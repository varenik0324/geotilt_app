import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import re
import logging
import sqlite3
import requests
import os
import sys
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------
CONFIG = {
    "BOT_TOKEN": "8538186715:AAG7XsBxp6TAy2lalWQ6_KkBkrUIEZCqxuw",
    "CHAT_ID": "1278271780",
    "LOG_FILE": "app_errors.log",
    "DB_FILE": "measurements.db",
    "DEFAULT_K_EM15H": 0.0031559,
    "DEFAULT_K_SM25H": 0.0035708,
    "F_STRING": 12.2,
    "F_CONCRETE": 10.0,
    "E_MODULUS": 3_000_000,
    "PILE_A": 6.51e-08,
    "PILE_B": -0.02931,
    "PILE_C": 248.4372,
    "PILE_K": -0.036375,
    "PILE_T_REF": 23.9,
}

# ------------------------------------------------------------
# ЛОГГИРОВАНИЕ
# ------------------------------------------------------------
logging.basicConfig(
    filename=CONFIG["LOG_FILE"],
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ------------------------------------------------------------
# УТИЛИТЫ
# ------------------------------------------------------------
def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

def send_telegram(message: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{CONFIG['BOT_TOKEN']}/sendMessage"
        payload = {"chat_id": CONFIG['CHAT_ID'], "text": f"📩 {message}", "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except Exception as e:
        logging.error(f"Telegram exception: {e}")
        return False

def clean_numeric(val):
    if pd.isna(val):
        return np.nan
    if isinstance(val, str):
        val = val.replace(',', '.').replace(' ', '').strip()
        if val == '' or val == '-':
            return np.nan
        try:
            return float(val)
        except ValueError:
            return np.nan
    return val

# ------------------------------------------------------------
# СПЕЦИФИКАЦИИ ДАТЧИКОВ
# ------------------------------------------------------------
SENSOR_SPECS = {...}  # оставлен без изменений для краткости, но в реальном коде он должен быть полным

def get_sensor_specs(sensor_type: str) -> str:
    # ... (без изменений)
    return ""

# ------------------------------------------------------------
# ОБРАБОТЧИК ТЕНЗОДАТЧИКОВ (плоские таблицы)
# ------------------------------------------------------------
class DataProcessor:
    # ... (без изменений)
    pass

# ------------------------------------------------------------
# ГЕНЕРАЦИЯ ОТЧЁТОВ
# ------------------------------------------------------------
class ReportGenerator:
    # ... (без изменений)
    pass

# ------------------------------------------------------------
# ПАРСЕР СВАЙНЫХ ИСПЫТАНИЙ (ГИБКАЯ ВЕРСИЯ)
# ------------------------------------------------------------
class PileParser:
    @staticmethod
    def find_sheets(file_bytes: bytes) -> Tuple[str, List[str]]:
        xl = pd.ExcelFile(file_bytes)
        sheets = xl.sheet_names

        test_sheet = None
        zero_sheets = []

        # Ищем лист испытаний
        for name in sheets:
            if 'испытания' in name.lower() or 'испыт' in name.lower():
                test_sheet = name
                break
        if test_sheet is None:
            for name in sheets:
                df_sample = pd.read_excel(file_bytes, sheet_name=name, nrows=30, header=None)
                for _, row in df_sample.iterrows():
                    row_text = ' '.join([str(c) for c in row if pd.notna(c)])
                    if 'Нагрузка, тс' in row_text and 'Давление, бар' in row_text:
                        test_sheet = name
                        break
                if test_sheet:
                    break

        # Ищем нулевые листы
        for name in sheets:
            if name == test_sheet:
                continue
            if 'свая' in name.lower() or 'нулевой' in name.lower():
                zero_sheets.append(name)
            else:
                df_sample = pd.read_excel(file_bytes, sheet_name=name, nrows=30, header=None)
                for _, row in df_sample.iterrows():
                    row_text = ' '.join([str(c) for c in row if pd.notna(c)])
                    if 'Частота' in row_text and 'Температура' in row_text:
                        zero_sheets.append(name)
                        break

        return test_sheet, zero_sheets

    @staticmethod
    def _extract_zero_data(df_zero_raw: pd.DataFrame) -> Dict:
        zero_data = {}
        freq_col, temp_col = None, None
        header_row = None

        for idx, row in df_zero_raw.iterrows():
            row_text = ' '.join([str(c) for c in row if pd.notna(c)])
            if 'Частота' in row_text and 'Температура' in row_text:
                for i, cell in enumerate(row):
                    if isinstance(cell, str):
                        if 'Частота' in cell:
                            freq_col = i
                        if 'Температура' in cell:
                            temp_col = i
                if freq_col is not None and temp_col is not None:
                    header_row = idx
                    break

        if header_row is None:
            return zero_data

        sensor_pattern = re.compile(r'(\d+)[-–]?\s*й?\s*(верх|сред|низ)', re.IGNORECASE)
        for idx in range(header_row + 1, len(df_zero_raw)):
            row = df_zero_raw.iloc[idx]
            first_cell = str(row[0]).strip() if len(row) > 0 else ''
            if not first_cell:
                continue
            if sensor_pattern.search(first_cell) or any(kw in first_cell.lower() for kw in ['верх', 'сред', 'низ']):
                sensor_name = first_cell
                f_val = row[freq_col] if freq_col < len(row) and pd.notna(row[freq_col]) else np.nan
                t_val = row[temp_col] if temp_col < len(row) and pd.notna(row[temp_col]) else np.nan
                if not pd.isna(f_val) and not pd.isna(t_val):
                    zero_data[sensor_name] = {'f0': f_val, 'T0': t_val}
        return zero_data

    @staticmethod
    def _find_header_blocks(df_test_raw: pd.DataFrame) -> List[Dict]:
        """
        Находит все строки-заголовки блоков (содержат одновременно "Время", "Нагрузка", "Давление").
        Возвращает список словарей с номерами строк начала и конца каждого блока.
        """
        header_rows = []
        for idx, row in df_test_raw.iterrows():
            row_text = ' '.join([str(c) for c in row if pd.notna(c)])
            row_lower = row_text.lower()
            if ('время' in row_lower or 'время,' in row_lower) and \
               ('нагрузка' in row_lower or 'нагрузка,' in row_lower) and \
               ('давление' in row_lower or 'давление,' in row_lower):
                header_rows.append(idx)

        blocks = []
        for i, h_row in enumerate(header_rows):
            # Определяем имя сваи (строка над заголовком, содержащая "Свая")
            pile_name = None
            for offset in range(1, 5):
                if h_row - offset >= 0:
                    cell = df_test_raw.iloc[h_row - offset, 0]
                    if pd.notna(cell) and 'Свая' in str(cell):
                        pile_name = str(cell).strip()
                        break
            if pile_name is None:
                pile_name = f"Блок_{i+1}"
            end_row = header_rows[i+1] if i+1 < len(header_rows) else len(df_test_raw)
            blocks.append({
                'name': pile_name,
                'start_header': h_row,
                'end': end_row
            })
        return blocks

    @staticmethod
    def _extract_block_data(df_test_raw: pd.DataFrame, start_header: int, end_row: int,
                            zero_data: Dict) -> Dict[str, pd.DataFrame]:
        # Извлекаем заголовки
        headers = df_test_raw.iloc[start_header].tolist()
        headers = [str(h).strip() if pd.notna(h) else '' for h in headers]

        # Определяем ступени
        step_columns = {}
        current_step = None
        step_pattern = re.compile(r'Ступень\s*(\d+)', re.IGNORECASE)
        for i, h in enumerate(headers):
            match = step_pattern.search(h)
            if match:
                current_step = int(match.group(1))
                step_columns[current_step] = {}
            elif current_step is not None and h:
                if 'Время' in h or 'время' in h:
                    step_columns[current_step]['Время'] = i
                elif 'Нагрузка' in h or 'нагрузка' in h:
                    step_columns[current_step]['Нагрузка'] = i
                elif 'Давление' in h or 'давление' in h:
                    step_columns[current_step]['Давление'] = i
                elif 'Частота' in h or 'частота' in h:
                    step_columns[current_step]['Частота'] = i
                elif 'Температура' in h or 'температура' in h:
                    step_columns[current_step]['Температура'] = i

        if not step_columns:
            step_columns[1] = {}
            for i, h in enumerate(headers):
                if 'Время' in h or 'время' in h:
                    step_columns[1]['Время'] = i
                elif 'Нагрузка' in h or 'нагрузка' in h:
                    step_columns[1]['Нагрузка'] = i
                elif 'Давление' in h or 'давление' in h:
                    step_columns[1]['Давление'] = i
                elif 'Частота' in h or 'частота' in h:
                    step_columns[1]['Частота'] = i
                elif 'Температура' in h or 'температура' in h:
                    step_columns[1]['Температура'] = i

        # Ищем строки с датчиками
        sensor_rows = []
        exclude_phrases = ['Верх сваи', 'Низ сваи', 'Под пятой', 'уровень']
        sensor_pattern = re.compile(r'(\d+)[-–]?\s*й?\s*(верх|сред|низ)', re.IGNORECASE)
        for idx in range(start_header + 1, end_row):
            row = df_test_raw.iloc[idx]
            first_cell = str(row[0]).strip() if len(row) > 0 else ''
            if not first_cell:
                continue
            if any(phrase in first_cell for phrase in exclude_phrases):
                continue
            if sensor_pattern.search(first_cell) or any(kw in first_cell.lower() for kw in ['верх', 'сред', 'низ']):
                sensor_rows.append(idx)

        # Собираем данные
        block_results = {}
        for idx in sensor_rows:
            row = df_test_raw.iloc[idx]
            sensor_name = str(row[0]).strip() if len(row) > 0 else f"Датчик_{idx}"
            sensor_data = []
            for step, cols in step_columns.items():
                if 'Нагрузка' not in cols or 'Давление' not in cols:
                    continue
                time_val = row[cols['Время']] if cols.get('Время') is not None and cols['Время'] < len(row) else None
                load_val = row[cols['Нагрузка']] if cols['Нагрузка'] < len(row) else None
                press_val = row[cols['Давление']] if cols['Давление'] < len(row) else None
                freq_val = row[cols.get('Частота')] if cols.get('Частота') is not None and cols['Частота'] < len(row) else None
                temp_val = row[cols.get('Температура')] if cols.get('Температура') is not None and cols['Температура'] < len(row) else None

                sensor_data.append({
                    'Ступень': step,
                    'Время': clean_numeric(time_val),
                    'Нагрузка, тс': clean_numeric(load_val),
                    'Давление, бар': clean_numeric(press_val),
                    'Частота, Гц': clean_numeric(freq_val),
                    'Температура, °С': clean_numeric(temp_val)
                })

            if sensor_data:
                df_sensor = pd.DataFrame(sensor_data)
                # Если есть нулевые данные для этого датчика, рассчитываем давление
                if sensor_name in zero_data:
                    f0 = zero_data[sensor_name]['f0']
                    T0 = zero_data[sensor_name]['T0']
                    if not pd.isna(f0) and not pd.isna(T0):
                        A = CONFIG["PILE_A"]
                        B = CONFIG["PILE_B"]
                        C = CONFIG["PILE_C"]
                        K = CONFIG["PILE_K"]
                        T_ref = CONFIG["PILE_T_REF"]
                        df_sensor['Давление_расч, Psi'] = np.nan
                        df_sensor['Давление_расч, МПа'] = np.nan
                        for i, r in df_sensor.iterrows():
                            f = r['Частота, Гц']
                            T = r['Температура, °С']
                            if not pd.isna(f) and not pd.isna(T):
                                Psi = A * (f**2) + B * f + C + K * (T - T_ref)
                                df_sensor.at[i, 'Давление_расч, Psi'] = Psi
                                df_sensor.at[i, 'Давление_расч, МПа'] = Psi * 0.00689475729317831
                block_results[sensor_name] = df_sensor

        return block_results

    @staticmethod
    @st.cache_data
    def parse_pile_data(file_bytes: bytes) -> Tuple[Dict[str, pd.DataFrame], Dict]:
        test_sheet, zero_sheets = PileParser.find_sheets(file_bytes)
        info = {
            'test_sheet': test_sheet,
            'zero_sheets': zero_sheets,
            'debug': []
        }

        if test_sheet is None:
            info['debug'].append("Лист испытаний не найден.")
            return {}, info
        if not zero_sheets:
            info['debug'].append("Нулевые листы не найдены.")
            return {}, info

        info['debug'].append(f"Лист испытаний: {test_sheet}")
        info['debug'].append(f"Нулевые листы: {zero_sheets}")

        df_test_raw = pd.read_excel(file_bytes, sheet_name=test_sheet, header=None)
        df_test_raw.columns = range(df_test_raw.shape[1])

        # Находим блоки
        blocks = PileParser._find_header_blocks(df_test_raw)
        if not blocks:
            info['debug'].append("Не найдены блоки с заголовками (нет строк с Время, Нагрузка, Давление).")
            return {}, info

        info['debug'].append(f"Найдено блоков: {len(blocks)}")

        # Парсим нулевые данные
        zero_data = {}
        for sheet in zero_sheets:
            df_zero_raw = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            df_zero_raw.columns = range(df_zero_raw.shape[1])
            zero_data.update(PileParser._extract_zero_data(df_zero_raw))

        info['debug'].append(f"Нулевых значений получено: {len(zero_data)}")

        # Обрабатываем каждый блок
        all_results = {}
        for block in blocks:
            block_results = PileParser._extract_block_data(
                df_test_raw,
                block['start_header'],
                block['end'],
                zero_data
            )
            all_results.update(block_results)

        info['debug'].append(f"Обработано датчиков: {len(all_results)}")
        return all_results, info

# ------------------------------------------------------------
# ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ СВАЙНЫХ ИСПЫТАНИЙ
# ------------------------------------------------------------
def display_pile_results(results: Dict[str, pd.DataFrame], info: Dict):
    if not results:
        st.error("Не удалось извлечь данные. Проверьте структуру файла.")
        with st.expander("🔍 Отладка"):
            for msg in info.get('debug', []):
                st.write(msg)
        return

    st.success(f"✅ Обработано датчиков: {len(results)}")
    with st.expander("🔍 Отладка", expanded=False):
        for msg in info.get('debug', []):
            st.write(msg)

    sensor_names = list(results.keys())
    selected_sensors = st.multiselect("Выберите датчики для отображения", sensor_names, default=sensor_names[:3])

    for sensor in selected_sensors:
        df_sensor = results[sensor]
        with st.expander(f"📊 Датчик: {sensor} (строк: {len(df_sensor)})", expanded=True):
            st.dataframe(df_sensor)

            if 'Нагрузка, тс' in df_sensor.columns and 'Давление, бар' in df_sensor.columns:
                plot_df = df_sensor.dropna(subset=['Нагрузка, тс', 'Давление, бар'])
                if not plot_df.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=plot_df['Нагрузка, тс'],
                        y=plot_df['Давление, бар'],
                        mode='lines+markers',
                        name='Давление (из файла)'
                    ))
                    if 'Давление_расч, МПа' in plot_df.columns:
                        fig.add_trace(go.Scatter(
                            x=plot_df['Нагрузка, тс'],
                            y=plot_df['Давление_расч, МПа'] * 10,
                            mode='lines+markers',
                            name='Давление (расч.)'
                        ))
                    fig.update_layout(
                        title=f"Зависимость давления от нагрузки ({sensor})",
                        xaxis_title="Нагрузка, тс",
                        yaxis_title="Давление, бар",
                        template=st.session_state.get('template', 'plotly_white')
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Нет данных для построения графика.")

            csv = df_sensor.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label=f"📥 Скачать CSV для {sensor}",
                data=csv,
                file_name=f"{sensor}.csv",
                mime="text/csv",
                key=f"download_csv_{sensor}"
            )

# ------------------------------------------------------------
# ОСНОВНОЕ ПРИЛОЖЕНИЕ
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title="Анализ датчиков", layout="wide")
    st.title("📊 Обработка данных тензодатчиков")

    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'stats' not in st.session_state:
        st.session_state.stats = None
    if 'sensor_name' not in st.session_state:
        st.session_state.sensor_name = ""
    if 'template' not in st.session_state:
        st.session_state.template = 'plotly_white'

    # Боковая панель
    with st.sidebar:
        st.header("Настройки датчика")
        sensor_type = st.selectbox(
            "Тип датчика",
            list(SENSOR_SPECS.keys()),
            index=0,
            key="sensor_type"
        )
        # ... (остальное без изменений)

    # Вкладки
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📂 Загрузка файла",
        "✏️ Ручной ввод",
        "🧪 Свайные испытания",
        "📋 Подбор датчиков",
        "📈 Интерактивная калибровка",
        "📊 Сравнение датчиков"
    ])

    # Вкладка 1 и 2 без изменений...
    with tab1:
        st.subheader("Загрузка файла с данными (плоская таблица)")
        # ... (как было)

    with tab2:
        st.subheader("Ручной ввод")
        # ... (как было)

    # ---------- Вкладка 3: Свайные испытания ----------
    with tab3:
        st.subheader("📂 Загрузка файла с испытаниями свай")
        st.markdown("""
        **Универсальный парсер** обработает файлы со сложной структурой.
        Если автоматика не сработает, попробуйте вручную указать параметры в разделе ниже.
        """)

        uploaded_pile = st.file_uploader("Выберите файл .xlsx", type=["xlsx"], key="pile_uploader_new")

        if uploaded_pile is not None:
            file_bytes = uploaded_pile.read()
            # Показываем превью первых 30 строк для ручной настройки
            df_preview = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=None, nrows=30)
            st.subheader("Превью файла (первые 30 строк)")
            st.dataframe(df_preview)

            with st.expander("⚙️ Ручная настройка парсинга (если автоматика не сработала)"):
                st.markdown("""
                Укажите вручную:
                - **Строка с заголовками (0-индекс)** – строка, где написаны "Время, ч", "Нагрузка, тс", "Давление, бар".
                - **Столбец с названиями датчиков (0-индекс)** – обычно 0.
                - **Лист с нулевыми значениями** – выберите из списка.
                """)
                manual_header_row = st.number_input("Строка заголовков (0-индекс)", min_value=0, max_value=50, value=4, step=1)
                manual_sensor_col = st.number_input("Столбец с названиями датчиков (0-индекс)", min_value=0, max_value=20, value=0, step=1)
                zero_sheet_manual = st.selectbox("Лист с нулевыми значениями", options=pd.ExcelFile(io.BytesIO(file_bytes)).sheet_names, index=0)

            try:
                with st.spinner("Обработка файла..."):
                    results, info = PileParser.parse_pile_data(file_bytes)
                display_pile_results(results, info)
            except Exception as e:
                st.error(f"Ошибка при автоматическом парсинге: {e}")
                st.info("Попробуйте использовать ручную настройку или проверьте структуру файла.")
                logging.error(f"Ошибка в свайном парсере: {e}")
                send_telegram(f"Ошибка в свайном парсере: {e}")

    # Вкладки 4-6 без изменений...

if __name__ == "__main__":
    main()
