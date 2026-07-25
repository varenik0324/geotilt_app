import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import os
import sys
import re
import logging
import sqlite3
import requests
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
class Config:
    BOT_TOKEN = "8538186715:AAG7XsBxp6TAy2lalWQ6_KkBkrUIEZCqxuw"
    CHAT_ID = "1278271780"
    LOG_FILE = "app_errors.log"
    DB_FILE = "measurements.db"
    DEFAULT_K_EM15H = 0.0031559
    DEFAULT_K_SM25H = 0.0035708
    F_STRING = 12.2
    F_CONCRETE = 10.0
    E_MODULUS = 3_000_000
    PILE_A = 6.51e-08
    PILE_B = -0.02931
    PILE_C = 248.4372
    PILE_K = -0.036375
    PILE_T_REF = 23.9

    SENSOR_SPECS = {
        "MAS‑VWS‑EM15H (встроенный)": {
            "name": "MAS‑VWS‑EM15H (встроенный)",
            "type": "Виброструнный тензометр",
            "measuring_range": "±1500 μϵ",
            "accuracy": "0.5% F.S",
            "resolution": "1.0 μϵ",
            "temperature_range": "-20…+80 °C",
            "temperature_accuracy": "±0.5 °C",
            "waterproof": "≥0.5 МПа",
            "gauge_length": "150 мм",
            "k_factor": "0.0031559",
            "thermal_expansion_steel": "12.2 μϵ/°C",
            "thermal_expansion_concrete": "10.0 μϵ/°C",
            "description": "Виброструнный тензометр для измерения деформаций на поверхностях бетонных и стальных конструкций.",
            "application": "Мониторинг мостов, зданий, плотин, труб, свай."
        },
        "MAS‑VWS‑SM15 (поверхностный)": {
            "name": "MAS‑VWS‑SM15 (поверхностный)",
            "type": "Виброструнный тензометр (короткая база)",
            "measuring_range": "±1500 μϵ",
            "accuracy": "0.5% F.S",
            "resolution": "1.0 μϵ",
            "temperature_range": "-20…+80 °C",
            "temperature_accuracy": "±0.5 °C",
            "waterproof": "≥0.5 МПа",
            "gauge_length": "150 мм",
            "k_factor": "G × C (задаётся пользователем)",
            "thermal_expansion_steel": "12.2 μϵ/°C",
            "thermal_expansion_concrete": "10.0 μϵ/°C",
            "description": "Виброструнный тензометр с длиной базы 150 мм для измерения деформаций на бетонных и стальных поверхностях.",
            "application": "Мониторинг строительных конструкций, мостов, тоннелей, свай."
        },
        "MAS‑VWS‑SM25H (поверхностный длинная база)": {
            "name": "MAS‑VWS‑SM25H (поверхностный длинная база)",
            "type": "Виброструнный тензометр (длинная база)",
            "measuring_range": "±2500 μϵ",
            "accuracy": "0.5% F.S",
            "resolution": "0.1 μϵ",
            "temperature_range": "-40…+90 °C",
            "temperature_accuracy": "±0.5 °C",
            "waterproof": "≥0.5 МПа",
            "gauge_length": "129 мм",
            "k_factor": "0.0035708",
            "thermal_expansion_steel": "12.2 μϵ/°C",
            "thermal_expansion_concrete": "10.0 μϵ/°C",
            "description": "Виброструнный тензометр с длинной базой 129 мм для измерения деформаций на поверхностях бетонных и стальных конструкций.",
            "application": "Мониторинг больших конструкций (плотины, мосты, тоннели)."
        },
        "MAS‑VWE (давление грунта)": {
            "name": "MAS‑VWE (давление грунта)",
            "type": "Виброструнный датчик давления грунта",
            "measuring_range": "0…350/700/1000/2000/3000 кПа",
            "accuracy": "0.5% F.S",
            "resolution": "0.01 кПа (по частоте)",
            "temperature_range": "-40…+80 °C",
            "temperature_accuracy": "±0.5 °C (@ -10…70 °C)",
            "waterproof": "≥1.0 МПа",
            "k_factor": "G × C (задаётся пользователем)",
            "thermal_expansion_steel": "12.2 μϵ/°C (для стали)",
            "thermal_expansion_concrete": "10.0 μϵ/°C (для бетона)",
            "description": "Виброструнный датчик давления грунта для измерения напряжений в массиве грунта, насыпях, основаниях фундаментов.",
            "application": "Мониторинг земляных плотин, откосов, дорожных насыпей, подпорных стен, тоннелей."
        }
    }

    @classmethod
    def get_sensor_specs(cls, sensor_type: str) -> str:
        specs = cls.SENSOR_SPECS.get(sensor_type)
        if not specs:
            return "Характеристики не найдены."
        lines = [
            f"Тип датчика: {specs.get('name', 'не указан')}",
            f"Назначение: {specs.get('type', 'не указано')}",
            f"Диапазон измерений: {specs.get('measuring_range', 'не указан')}",
            f"Точность: {specs.get('accuracy', 'не указана')}",
            f"Разрешение: {specs.get('resolution', 'не указано')}",
            f"Диапазон температур: {specs.get('temperature_range', 'не указан')}",
            f"Точность температуры: {specs.get('temperature_accuracy', 'не указана')}",
            f"Водонепроницаемость: {specs.get('waterproof', 'не указана')}",
            f"Коэффициент K: {specs.get('k_factor', 'не указан')}",
            f"Коэф. теплового расширения (сталь): {specs.get('thermal_expansion_steel', 'не указан')}",
            f"Коэф. теплового расширения (бетон): {specs.get('thermal_expansion_concrete', 'не указан')}",
            f"Описание: {specs.get('description', 'не указано')}",
            f"Области применения: {specs.get('application', 'не указаны')}"
        ]
        return "\n".join(lines)

# ============================================================
# 2. УТИЛИТЫ
# ============================================================
class Utils:
    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, relative_path)

    @staticmethod
    def send_telegram(message: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage"
            payload = {"chat_id": Config.CHAT_ID, "text": f"📩 {message}", "parse_mode": "HTML"}
            r = requests.post(url, json=payload, timeout=5)
            return r.status_code == 200
        except Exception as e:
            logging.error(f"Telegram exception: {e}")
            return False

    @staticmethod
    def clean_numeric(val):
        if pd.isna(val):
            return np.nan
        if isinstance(val, str):
            val = val.replace(',', '.').replace(' ', '').strip()
            if val == '' or val == '-':
                return np.nan
            try:
                return float(val)
            except:
                return np.nan
        return val

# ============================================================
# 3. ОЧИСТКА И ВАЛИДАЦИЯ ДАННЫХ
# ============================================================
class DataCleaner:
    @staticmethod
    def to_numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series(index=df.index, dtype=float)
        series = df[col].astype(str).str.replace(',', '.').str.replace(' ', '').str.strip()
        series = series.replace('', np.nan)
        return pd.to_numeric(series, errors='coerce')

    @staticmethod
    def validate_three_columns(df: pd.DataFrame) -> Tuple[bool, str, pd.DataFrame]:
        required = ['load', 'freq', 'temp']
        if df.empty:
            return False, "DataFrame пуст.", df
        missing = [c for c in required if c not in df.columns]
        if missing:
            return False, f"Отсутствуют столбцы: {', '.join(missing)}", df
        df_clean = df.copy()
        errors = []
        for col in required:
            converted = DataCleaner.to_numeric_series(df_clean, col)
            invalid_mask = converted.isna()
            if invalid_mask.any():
                invalid_rows = df_clean.index[invalid_mask].tolist()
                errors.append(f"В столбце '{col}' проблемы в строках: {invalid_rows[:10]}{'...' if len(invalid_rows)>10 else ''}")
            df_clean[col] = converted
        df_clean = df_clean.dropna(subset=required, how='all')
        for col in required:
            if df_clean[col].isna().sum() > 0:
                df_clean[col] = df_clean[col].interpolate(method='linear', limit=5)
        df_clean = df_clean.dropna(subset=required)
        if df_clean.empty:
            return False, "После очистки не осталось числовых строк. Проверьте данные.", df_clean
        if errors:
            msg = "Обнаружены проблемы с данными:\n" + "\n".join(errors) + "\nПроблемные строки были удалены."
            return True, msg, df_clean
        else:
            return True, "Данные успешно проверены.", df_clean

# ============================================================
# 4. РАСЧЁТ ДЕФОРМАЦИЙ
# ============================================================
class StrainCalculator:
    @staticmethod
    def compute_strain(df: pd.DataFrame, f0: float, t0: float,
                       sensor_type: str, g_val: Optional[float] = None,
                       c_val: Optional[float] = None) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        if df.empty:
            return None, None
        if sensor_type == 'MAS‑VWS‑EM15H (встроенный)':
            K = Config.DEFAULT_K_EM15H
        elif sensor_type == 'MAS‑VWS‑SM25H (поверхностный длинная база)':
            K = Config.DEFAULT_K_SM25H
        elif sensor_type in ['MAS‑VWS‑SM15 (поверхностный)', 'MAS‑VWE (давление грунта)']:
            if g_val is None or c_val is None:
                return None, None
            K = g_val * c_val
        else:
            return None, None
        df = df.copy()
        df['strain'] = K * (df['freq']**2 - f0**2) + (df['temp'] - t0) * (Config.F_STRING - Config.F_CONCRETE)
        df['stress_MPa'] = Config.E_MODULUS * df['strain'] / 1_000_000 * 0.00689476
        stats = {
            'Количество точек': len(df),
            'Средняя деформация, μϵ': df['strain'].mean(),
            'Макс. деформация, μϵ': df['strain'].max(),
            'Мин. деформация, μϵ': df['strain'].min(),
            'Среднее напряжение, МПа': df['stress_MPa'].mean(),
            'Макс. напряжение, МПа': df['stress_MPa'].max(),
            'Мин. напряжение, МПа': df['stress_MPa'].min(),
        }
        return df, stats

# ============================================================
# 5. ГЕНЕРАЦИЯ ОТЧЁТОВ
# ============================================================
class ReportBuilder:
    @staticmethod
    def to_excel(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Результат')
            stats_df = pd.DataFrame.from_dict(stats, orient='index', columns=['Значение'])
            stats_df.to_excel(writer, sheet_name='Сводка')
            ws_spec = writer.book.add_worksheet('Спецификация датчика')
            specs_text = Config.get_sensor_specs(sensor_type)
            row = 0
            for line in specs_text.split('\n'):
                ws_spec.write(row, 0, line)
                row += 1
        return output.getvalue()

    @staticmethod
    def to_pdf(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
               f0: float, t0: float) -> io.BytesIO:
        # Заглушка – можно реализовать при необходимости
        return io.BytesIO()

    @staticmethod
    def to_word(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
                f0: float, t0: float) -> io.BytesIO:
        # Заглушка
        return io.BytesIO()

# ============================================================
# 6. ПАРСЕР СВАЙНЫХ ИСПЫТАНИЙ
# ============================================================
class PileParser:
    @staticmethod
    def parse_manual(df_test: pd.DataFrame, df_zero: pd.DataFrame,
                     header_row: int, data_start: int, sensor_col: int,
                     zero_freq_col: int = None, zero_temp_col: int = None) -> Dict[str, pd.DataFrame]:
        headers = df_test.iloc[header_row].tolist()
        headers = [str(h).strip() if pd.notna(h) else '' for h in headers]

        step_columns = {}
        current_step = None
        step_pattern = re.compile(r'Ступень\s*(\d+)', re.IGNORECASE)
        for i, h in enumerate(headers):
            match = step_pattern.search(h)
            if match:
                step_num = int(match.group(1))
                current_step = step_num
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

        # Ищем строки датчиков
        sensor_rows = []
        for idx in range(data_start, len(df_test)):
            row = df_test.iloc[idx]
            first_cell = str(row[sensor_col]).strip() if sensor_col < len(row) else ''
            if re.search(r'\d-й\s*(верх|сред|низ)', first_cell, re.IGNORECASE) or \
               re.search(r'(верх|сред|низ)', first_cell, re.IGNORECASE):
                sensor_rows.append(idx)
            elif first_cell == '':
                for step, cols in step_columns.items():
                    if 'Нагрузка' in cols and cols['Нагрузка'] < len(row):
                        val = row[cols['Нагрузка']]
                        if pd.notna(val) and isinstance(val, (int, float)):
                            sensor_rows.append(idx)
                            break

        # Парсинг нулевых значений
        zero_data = {}
        zero_sensor_rows = []
        for idx in range(len(df_zero)):
            row = df_zero.iloc[idx]
            first_cell = str(row[0]).strip() if 0 < len(row) else ''
            if re.search(r'\d-й\s*(верх|сред|низ)', first_cell, re.IGNORECASE) or \
               re.search(r'(верх|сред|низ)', first_cell, re.IGNORECASE):
                zero_sensor_rows.append(idx)

        if zero_freq_col is not None and zero_temp_col is not None:
            for idx in zero_sensor_rows:
                row = df_zero.iloc[idx]
                sensor_name = str(row[0]).strip()
                freq_val = row[zero_freq_col] if zero_freq_col < len(row) and pd.notna(row[zero_freq_col]) else np.nan
                temp_val = row[zero_temp_col] if zero_temp_col < len(row) and pd.notna(row[zero_temp_col]) else np.nan
                zero_data[sensor_name] = {'f0': freq_val, 'T0': temp_val}

        results = {}
        for idx in sensor_rows:
            row = df_test.iloc[idx]
            sensor_name = str(row[sensor_col]).strip() if sensor_col < len(row) else f"Датчик_{idx}"
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
                    'Время': Utils.clean_numeric(time_val),
                    'Нагрузка, тс': Utils.clean_numeric(load_val),
                    'Давление, бар': Utils.clean_numeric(press_val),
                    'Частота, Гц': Utils.clean_numeric(freq_val),
                    'Температура, °С': Utils.clean_numeric(temp_val)
                })

            if sensor_data:
                df_sensor = pd.DataFrame(sensor_data)
                if sensor_name in zero_data:
                    f0 = zero_data[sensor_name]['f0']
                    T0 = zero_data[sensor_name]['T0']
                    if not pd.isna(f0) and not pd.isna(T0):
                        A = Config.PILE_A
                        B = Config.PILE_B
                        C = Config.PILE_C
                        K = Config.PILE_K
                        T_ref = Config.PILE_T_REF
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

        return results

# ============================================================
# 7. ВСПОМОГАТЕЛЬНЫЕ UI-ФУНКЦИИ
# ============================================================
def display_strain_results(result: pd.DataFrame, stats: Dict, sensor_name: str,
                           sensor_type: str, f0: float, t0: float):
    st.subheader("✅ Результат обработки")
    st.dataframe(result)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result['load'], y=result['strain'], mode='lines+markers', name='Деформация, μϵ'))
    fig.update_layout(
        title="Деформация от нагрузки",
        xaxis_title="Нагрузка, тс",
        yaxis_title="Деформация, μϵ",
        template=st.session_state.get('template', 'plotly_white')
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📥 Скачать отчёт")
    col1, col2, col3 = st.columns(3)
    with col1:
        excel_data = ReportBuilder.to_excel(result, stats, sensor_name, sensor_type)
        st.download_button(
            label="📊 Excel",
            data=excel_data,
            file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_download"
        )
    with col2:
        pdf_data = ReportBuilder.to_pdf(result, stats, sensor_name, sensor_type, f0, t0)
        st.download_button(
            label="📄 PDF",
            data=pdf_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            key="pdf_download"
        )
    with col3:
        word_data = ReportBuilder.to_word(result, stats, sensor_name, sensor_type, f0, t0)
        st.download_button(
            label="📝 Word",
            data=word_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="word_download"
        )

    st.subheader("💾 Сохранить в базу данных")
    if st.button("Сохранить текущий результат в базу"):
        if save_to_db(result, sensor_name):
            st.success("Данные сохранены в базу!")
        else:
            st.error("Ошибка сохранения в базу. Проверьте логи.")

def save_to_db(df: pd.DataFrame, sensor_name: str) -> bool:
    try:
        conn = sqlite3.connect(Config.DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sensor_name TEXT,
                      date TEXT,
                      load REAL,
                      freq REAL,
                      temp REAL,
                      strain REAL,
                      stress_MPa REAL)''')
        for _, row in df.iterrows():
            c.execute("INSERT INTO results (sensor_name, date, load, freq, temp, strain, stress_MPa) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (sensor_name, datetime.now().isoformat(), row['load'], row['freq'], row['temp'], row['strain'], row['stress_MPa']))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения в базу: {e}")
        return False

# ============================================================
# 8. ОСНОВНОЕ ПРИЛОЖЕНИЕ
# ============================================================
def main():
    st.set_page_config(page_title="Анализ датчиков", layout="wide")
    st.title("📊 Обработка данных тензодатчиков")

    # Инициализация состояния
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
            list(Config.SENSOR_SPECS.keys()),
            index=0,
            key="sensor_type"
        )
        st.markdown("---")
        st.markdown("**📋 Спецификация датчика**")
        specs = Config.SENSOR_SPECS.get(sensor_type)
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

        logo_path = Utils.get_resource_path("logo.png")
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
        uploaded_file = st.file_uploader("Выберите Excel-файл", type=["xlsx", "xls"], key="file_uploader_tab1")
        if uploaded_file:
            try:
                df_raw = pd.read_excel(uploaded_file)
                st.write("Превью:", df_raw.head())
                # Простой вариант – берём первые три колонки как load, freq, temp
                if len(df_raw.columns) >= 3:
                    df_mapped = df_raw.iloc[:, :3].copy()
                    df_mapped.columns = ['load', 'freq', 'temp']
                    valid, msg, df_clean = DataCleaner.validate_three_columns(df_mapped)
                    if valid:
                        st.success(msg)
                        result, stats = StrainCalculator.compute_strain(df_clean, f0, t0, sensor_type, g_val, c_val)
                        if result is not None:
                            st.session_state.result = result
                            st.session_state.stats = stats
                            st.session_state.sensor_name = uploaded_file.name
                            display_strain_results(result, stats, uploaded_file.name, sensor_type, f0, t0)
                        else:
                            st.error("Ошибка расчёта. Проверьте данные и настройки датчика.")
                    else:
                        st.error(msg)
                else:
                    st.warning("Файл должен содержать минимум 3 колонки.")
            except Exception as e:
                st.error(f"Ошибка: {e}")
                logging.error(f"Ошибка в загрузке: {e}")

    # ---------- Вкладка 2: Ручной ввод ----------
    with tab2:
        st.subheader("Вставьте данные из буфера обмена")
        st.markdown("Формат: нагрузка, частота, температура (разделитель – табуляция, запятая или пробел)")
        delimiter = st.selectbox("Разделитель", ["\\t (табуляция)", ", (запятая)", "; (точка с запятой)", "пробел"], key="delimiter")
        sep = {'\\t (табуляция)': '\t', ', (запятая)': ',', '; (точка с запятой)': ';', 'пробел': ' '}[delimiter]
        text_data = st.text_area("Введите данные", height=200)
        if st.button("Обработать"):
            if not text_data.strip():
                st.warning("Введите данные.")
            else:
                try:
                    lines = text_data.strip().splitlines()
                    rows = [line.split(sep) for line in lines if line.strip()]
                    rows = [[Utils.clean_numeric(x) for x in row[:3]] for row in rows if len(row) >= 3]
                    if not rows:
                        st.error("Не удалось распознать данные.")
                    else:
                        df_manual = pd.DataFrame(rows, columns=['load', 'freq', 'temp'])
                        valid, msg, df_clean = DataCleaner.validate_three_columns(df_manual)
                        if valid:
                            st.success(msg)
                            result, stats = StrainCalculator.compute_strain(df_clean, f0, t0, sensor_type, g_val, c_val)
                            if result is not None:
                                st.session_state.result = result
                                st.session_state.stats = stats
                                st.session_state.sensor_name = "Ручной ввод"
                                display_strain_results(result, stats, "Ручной ввод", sensor_type, f0, t0)
                            else:
                                st.error("Ошибка расчёта.")
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"Ошибка: {e}")

    # ---------- Вкладка 3: Свайные испытания ----------
    with tab3:
        st.subheader("Загрузка файла с испытаниями свай")
        st.markdown("Ручной парсинг: укажите номера строк и столбцов для вашего файла.")

        uploaded_pile = st.file_uploader("Выберите файл .xlsx", type=["xlsx"], key="pile_uploader")

        if uploaded_pile:
            try:
                xl = pd.ExcelFile(uploaded_pile)
                sheet_names = xl.sheet_names
                col1, col2 = st.columns(2)
                with col1:
                    test_sheet = st.selectbox("Лист с испытаниями", sheet_names, index=sheet_names.index('ИСПЫТАНИЯ') if 'ИСПЫТАНИЯ' in sheet_names else 0)
                with col2:
                    zero_sheet = st.selectbox("Лист с нулевыми значениями", sheet_names, index=0)

                df_test = pd.read_excel(uploaded_pile, sheet_name=test_sheet, header=None)
                df_zero = pd.read_excel(uploaded_pile, sheet_name=zero_sheet, header=None)

                st.subheader("Превью листа испытаний (первые 30 строк)")
                st.dataframe(df_test.head(30), use_container_width=True)

                st.subheader("Настройки парсинга")
                col3, col4, col5 = st.columns(3)
                with col3:
                    header_row = st.number_input("Строка заголовков (0-индекс)", min_value=0, max_value=50, value=4, step=1)
                with col4:
                    data_start = st.number_input("Строка с первым датчиком", min_value=0, max_value=50, value=6, step=1)
                with col5:
                    sensor_col = st.number_input("Столбец с названиями датчиков", min_value=0, max_value=20, value=0, step=1)

                # Определяем колонки частоты и температуры в нулевом листе
                zero_freq_col = None
                zero_temp_col = None
                for idx, row in df_zero.iterrows():
                    row_text = ' '.join([str(c) for c in row if pd.notna(c)])
                    if 'Частота' in row_text and 'Температура' in row_text:
                        for i, cell in enumerate(row):
                            if isinstance(cell, str):
                                if 'Частота' in cell:
                                    zero_freq_col = i
                                if 'Температура' in cell:
                                    zero_temp_col = i
                        break
                if zero_freq_col is None or zero_temp_col is None:
                    st.warning("Не удалось автоматически найти колонки частоты и температуры в нулевом листе. Укажите вручную.")
                    zero_freq_col = st.number_input("Столбец с частотой (0-индекс)", min_value=0, max_value=20, value=2, step=1)
                    zero_temp_col = st.number_input("Столбец с температурой (0-индекс)", min_value=0, max_value=20, value=3, step=1)

                if st.button("Распарсить", key="parse_pile"):
                    try:
                        results = PileParser.parse_manual(df_test, df_zero, header_row, data_start, sensor_col,
                                                          zero_freq_col, zero_temp_col)
                        if results:
                            st.success(f"✅ Обработано датчиков: {len(results)}")
                            sensor_names = list(results.keys())
                            selected = st.multiselect("Выберите датчики", sensor_names, default=sensor_names[:3])
                            for sensor in selected:
                                df_sensor = results[sensor]
                                with st.expander(f"📊 {sensor} (строк: {len(df_sensor)})", expanded=True):
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
                                                template=st.session_state.template
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
                        else:
                            st.error("Не удалось извлечь данные. Проверьте настройки.")
                    except Exception as e:
                        st.error(f"Ошибка парсинга: {e}")
                        logging.error(f"Ошибка парсинга: {e}")
                        Utils.send_telegram(f"Ошибка парсинга: {e}")

            except Exception as e:
                st.error(f"Ошибка: {e}")
                logging.error(f"Ошибка: {e}")

        else:
            st.info("Загрузите файл для начала работы.")

    # ---------- Вкладки 4-6 (заглушки – можно расширить) ----------
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
    # Настройка логирования
    logging.basicConfig(
        filename=Config.LOG_FILE,
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    main()
