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
    level=logging.ERROR,
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

# ------------------------------------------------------------
# СПЕЦИФИКАЦИИ ДАТЧИКОВ (кратко)
# ------------------------------------------------------------
SENSOR_SPECS = { ... }  # оставляем без изменений (полный словарь из предыдущих версий)

def get_sensor_specs(sensor_type: str) -> str:
    # ... (без изменений)
    return ""

# ------------------------------------------------------------
# ОБРАБОТЧИК ДАННЫХ (для тензодатчиков)
# ------------------------------------------------------------
class DataProcessor:
    # ... (код без изменений)
    pass

# ------------------------------------------------------------
# ГЕНЕРАЦИЯ ОТЧЁТОВ (заглушки)
# ------------------------------------------------------------
class ReportGenerator:
    # ... (заглушки)
    pass

# ------------------------------------------------------------
# НОВЫЙ ПАРСЕР СВАЙНЫХ ИСПЫТАНИЙ (АВТОМАТИЧЕСКИЙ)
# ------------------------------------------------------------
class PileParser:
    @staticmethod
    def find_sheets(file_bytes: bytes) -> Tuple[str, List[str]]:
        """
        Определяет лист с испытаниями и листы с нулевыми значениями.
        Возвращает (имя_листа_испытаний, список_нулевых_листов).
        """
        xl = pd.ExcelFile(file_bytes)
        sheets = xl.sheet_names

        test_sheet = None
        zero_sheets = []

        # Ищем лист испытаний: обычно содержит слова "испытания" или "испыт"
        for name in sheets:
            if 'испытания' in name.lower() or 'испыт' in name.lower():
                test_sheet = name
                break

        # Если не нашли, пробуем найти по наличию столбцов "Время, ч", "Нагрузка, тс" и т.д.
        if test_sheet is None:
            for name in sheets:
                df_sample = pd.read_excel(file_bytes, sheet_name=name, nrows=30, header=None)
                for idx, row in df_sample.iterrows():
                    row_text = ' '.join([str(c) for c in row if pd.notna(c)])
                    if 'Нагрузка, тс' in row_text and 'Давление, бар' in row_text:
                        test_sheet = name
                        break
                if test_sheet:
                    break

        # Ищем нулевые листы: обычно содержат "Свая" или "нулевой"
        for name in sheets:
            if name == test_sheet:
                continue
            if 'свая' in name.lower() or 'нулевой' in name.lower():
                zero_sheets.append(name)
            else:
                # Проверим, есть ли в листе столбцы "Частота" и "Температура"
                df_sample = pd.read_excel(file_bytes, sheet_name=name, nrows=30, header=None)
                for idx, row in df_sample.iterrows():
                    row_text = ' '.join([str(c) for c in row if pd.notna(c)])
                    if 'Частота' in row_text and 'Температура' in row_text:
                        zero_sheets.append(name)
                        break

        return test_sheet, zero_sheets

    @staticmethod
    def parse_pile_data(file_bytes: bytes) -> Tuple[Dict[str, pd.DataFrame], Dict]:
        """
        Основная функция парсинга. Возвращает:
        - results: словарь {название_датчика: DataFrame}
        - info: словарь с отладочной информацией
        """
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

        # Читаем лист испытаний
        df_test_raw = pd.read_excel(file_bytes, sheet_name=test_sheet, header=None)

        # Определяем строку заголовков (ищем строку с "Время, ч", "Нагрузка, тс", "Давление, бар")
        header_row = None
        for idx, row in df_test_raw.iterrows():
            row_text = ' '.join([str(c) for c in row if pd.notna(c)])
            if 'Время, ч' in row_text and 'Нагрузка, тс' in row_text and 'Давление, бар' in row_text:
                header_row = idx
                break

        if header_row is None:
            info['debug'].append("Не найдена строка заголовков.")
            return {}, info

        # Извлекаем заголовки
        headers = df_test_raw.iloc[header_row].tolist()
        headers = [str(h).strip() if pd.notna(h) else '' for h in headers]

        # Определяем ступени (колонки)
        step_columns = {}
        current_step = None
        step_pattern = re.compile(r'Ступень\s*(\d+)', re.IGNORECASE)
        for i, h in enumerate(headers):
            match = step_pattern.search(h)
            if match:
                current_step = int(match.group(1))
                step_columns[current_step] = {}
            elif current_step is not None and h:
                if 'Время' in h:
                    step_columns[current_step]['Время'] = i
                elif 'Нагрузка' in h:
                    step_columns[current_step]['Нагрузка'] = i
                elif 'Давление' in h:
                    step_columns[current_step]['Давление'] = i
                elif 'Частота' in h:
                    step_columns[current_step]['Частота'] = i
                elif 'Температура' in h:
                    step_columns[current_step]['Температура'] = i

        if not step_columns:
            info['debug'].append("Ступени не обнаружены. Создаём одну группу.")
            step_columns[1] = {}
            for i, h in enumerate(headers):
                if 'Время' in h:
                    step_columns[1]['Время'] = i
                elif 'Нагрузка' in h:
                    step_columns[1]['Нагрузка'] = i
                elif 'Давление' in h:
                    step_columns[1]['Давление'] = i
                elif 'Частота' in h:
                    step_columns[1]['Частота'] = i
                elif 'Температура' in h:
                    step_columns[1]['Температура'] = i

        info['debug'].append(f"Найдены ступени: {list(step_columns.keys())}")

        # Находим строки с датчиками (по первому столбцу, где есть "верх", "сред", "низ" или цифра-й)
        sensor_rows = []
        for idx in range(header_row + 1, len(df_test_raw)):
            row = df_test_raw.iloc[idx]
            first_cell = str(row[0]).strip() if len(row) > 0 else ''
            if re.search(r'\d-й\s*(верх|сред|низ)', first_cell, re.IGNORECASE) or \
               re.search(r'(верх|сред|низ)', first_cell, re.IGNORECASE):
                sensor_rows.append(idx)

        info['debug'].append(f"Найдено строк датчиков: {len(sensor_rows)}")

        if not sensor_rows:
            info['debug'].append("Датчики не найдены.")
            return {}, info

        # Парсим нулевые значения из всех нулевых листов
        zero_data = {}
        for sheet in zero_sheets:
            df_zero_raw = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            # Ищем строку с "Частота" и "Температура"
            freq_col = None
            temp_col = None
            zero_header_row = None
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
                        zero_header_row = idx
                        break
            if zero_header_row is None:
                info['debug'].append(f"В листе {sheet} не найдены заголовки Частота/Температура.")
                continue

            # Ищем строки датчиков
            for idx in range(zero_header_row + 1, len(df_zero_raw)):
                row = df_zero_raw.iloc[idx]
                first_cell = str(row[0]).strip() if len(row) > 0 else ''
                if re.search(r'\d-й\s*(верх|сред|низ)', first_cell, re.IGNORECASE) or \
                   re.search(r'(верх|сред|низ)', first_cell, re.IGNORECASE):
                    sensor_name = first_cell
                    f_val = row[freq_col] if freq_col < len(row) and pd.notna(row[freq_col]) else np.nan
                    t_val = row[temp_col] if temp_col < len(row) and pd.notna(row[temp_col]) else np.nan
                    if not pd.isna(f_val) and not pd.isna(t_val):
                        zero_data[sensor_name] = {'f0': f_val, 'T0': t_val}

        info['debug'].append(f"Нулевых значений получено: {len(zero_data)}")

        # Теперь собираем данные для каждого датчика
        results = {}
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

                def clean(v):
                    if pd.isna(v):
                        return np.nan
                    if isinstance(v, str):
                        v = v.replace(',', '.').replace(' ', '').strip()
                        if v == '' or v == '-':
                            return np.nan
                        try:
                            return float(v)
                        except:
                            return np.nan
                    return v

                sensor_data.append({
                    'Ступень': step,
                    'Время': clean(time_val),
                    'Нагрузка, тс': clean(load_val),
                    'Давление, бар': clean(press_val),
                    'Частота, Гц': clean(freq_val),
                    'Температура, °С': clean(temp_val)
                })

            if sensor_data:
                df_sensor = pd.DataFrame(sensor_data)
                # Если есть нулевые данные для этого датчика, рассчитаем давление по частоте
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
                results[sensor_name] = df_sensor

        info['debug'].append(f"Обработано датчиков: {len(results)}")
        return results, info

# ------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ UI-ФУНКЦИИ (для отображения результатов свайных испытаний)
# ------------------------------------------------------------
def display_pile_results(results: Dict[str, pd.DataFrame], info: Dict):
    if not results:
        st.error("Не удалось извлечь данные. Проверьте структуру файла.")
        with st.expander("🔍 Отладка"):
            for msg in info.get('debug', []):
                st.write(msg)
        return

    st.success(f"✅ Обработано датчиков: {len(results)}")
    with st.expander("🔍 Отладка"):
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
                            y=plot_df['Давление_расч, МПа'] * 10,  # переводим в бар для сравнения
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
                    st.info("Нет данных для построения графика (нет числовых значений нагрузки/давления).")

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

    # Боковая панель (без изменений, но с кратким содержанием)
    with st.sidebar:
        st.header("Настройки датчика")
        sensor_type = st.selectbox(
            "Тип датчика",
            list(SENSOR_SPECS.keys()),
            index=0,
            key="sensor_type"
        )
        st.markdown("---")
        st.markdown("**📋 Спецификация датчика**")
        specs = SENSOR_SPECS.get(sensor_type)
        if specs:
            st.markdown(f"**Тип:** {specs.get('type', 'не указан')}")
            st.markdown(f"**Диапазон:** {specs.get('measuring_range', 'не указан')}")
            st.markdown(f"**Точность:** {specs.get('accuracy', 'не указана')}")
            st.markdown(f"**Коэф. K:** {specs.get('k_factor', 'не указан')}")
            st.caption("Подробные характеристики будут включены в отчёт.")
        else:
            st.warning("Характеристики не найдены")

        g_val = None
        c_val = None
        if sensor_type in ["MAS‑VWS‑SM15 (поверхностный)", "MAS‑VWE (давление грунта)"]:
            st.subheader("Калибровочные коэффициенты")
            g_val = st.number_input("G", value=1.0, step=0.001, format="%.3f", key="g_val")
            c_val = st.number_input("C", value=1.0, step=0.001, format="%.3f", key="c_val")
            st.caption("Из сертификата датчика.")

        f0 = st.number_input("f₀ (Гц)", value=1000.0, step=0.1, format="%.1f", key="f0")
        t0 = st.number_input("T₀ (°C)", value=20.0, step=0.1, format="%.1f", key="t0")

        st.markdown("---")
        st.subheader("🎨 Оформление")
        theme = st.selectbox(
            "Тема графиков",
            ["Светлая", "Тёмная", "Корпоративная (синяя)"],
            index=0,
            key="theme"
        )
        if theme == "Светлая":
            st.session_state.template = "plotly_white"
        elif theme == "Тёмная":
            st.session_state.template = "plotly_dark"
        else:
            st.session_state.template = "seaborn"

        if st.button("Сохранить настройки"):
            st.success("Настройки сохранены!")

        logo_path = get_resource_path("logo.png")
        if os.path.exists(logo_path):
            try:
                st.image(logo_path, width=150)
            except:
                st.warning("Не удалось загрузить логотип")
        else:
            st.warning("Логотип не найден (файл logo.png)")

        st.markdown("### 🏗️ Геофундамент")
        st.caption("© 2026, все права защищены")

    # Вкладки
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📂 Загрузка файла",
        "✏️ Ручной ввод",
        "🧪 Свайные испытания",
        "📋 Подбор датчиков",
        "📈 Интерактивная калибровка",
        "📊 Сравнение датчиков"
    ])

    # ---------- Вкладка 1: Загрузка файла (плоская таблица) ----------
    with tab1:
        st.subheader("Загрузите файл с данными (плоская таблица)")
        st.markdown("Файл должен содержать колонки: нагрузка (load), частота (freq), температура (temp).")
        # ... (код для плоских таблиц оставляем как есть, либо делаем упрощённый вариант)
        st.info("Для свайных испытаний используйте вкладку 'Свайные испытания'.")

    # ---------- Вкладка 2: Ручной ввод ----------
    with tab2:
        st.subheader("Вставьте данные из буфера обмена")
        st.info("Вставьте данные в формате: нагрузка, частота, температура. Для свайных испытаний используйте вкладку 'Свайные испытания'.")

    # ---------- Вкладка 3: Свайные испытания (НОВЫЙ ПАРСЕР) ----------
    with tab3:
        st.subheader("📂 Загрузка файла с испытаниями свай")
        st.markdown("""
        **Автоматический парсер** обработает файлы со сложной структурой:
        - Найдёт листы с нулевыми значениями (Свая 39, Свая 52, ...) и лист испытаний.
        - Извлечёт данные по каждому датчику для всех ступеней нагрузки.
        - Рассчитает давление по частоте (если есть нулевые значения).
        - Построит графики зависимости давления от нагрузки.
        """)

        uploaded_pile = st.file_uploader("Выберите файл .xlsx", type=["xlsx"], key="pile_uploader_new")

        if uploaded_pile is not None:
            try:
                file_bytes = uploaded_pile.read()
                with st.spinner("Обработка файла..."):
                    results, info = PileParser.parse_pile_data(file_bytes)
                display_pile_results(results, info)
            except Exception as e:
                st.error(f"Ошибка обработки: {e}")
                logging.error(f"Ошибка в свайном парсере: {e}")
                send_telegram(f"Ошибка в свайном парсере: {e}")

    # ---------- Вкладки 4-6 (заглушки) ----------
    with tab4:
        st.subheader("📋 Подбор датчиков")
        st.info("Функция подбора датчиков будет добавлена в следующей версии.")

    with tab5:
        st.subheader("🎛️ Интерактивная калибровка")
        st.info("Интерактивная калибровка будет добавлена в следующей версии.")

    with tab6:
        st.subheader("📊 Сравнение датчиков")
        st.info("Сравнение датчиков будет добавлено в следующей версии.")

if __name__ == "__main__":
    main()
