import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import json
import os
import sys
import re
import logging
import sqlite3
import requests
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
# СПЕЦИФИКАЦИИ ДАТЧИКОВ
# ------------------------------------------------------------
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

def get_sensor_specs(sensor_type: str) -> str:
    specs = SENSOR_SPECS.get(sensor_type)
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

# ------------------------------------------------------------
# КЛАСС ДЛЯ ОБРАБОТКИ ДАННЫХ
# ------------------------------------------------------------
class DataProcessor:
    @staticmethod
    def clean_and_convert(df: pd.DataFrame, col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series(index=df.index, dtype=float)
        series = df[col].astype(str).str.replace(',', '.').str.replace(' ', '').str.strip()
        series = series.replace('', np.nan)
        return pd.to_numeric(series, errors='coerce')

    @staticmethod
    def validate_data(df: pd.DataFrame) -> Tuple[bool, str, pd.DataFrame]:
        """
        Проверяет данные на наличие всех колонок и числовых значений.
        Возвращает (успех, сообщение, DataFrame с исправленными/очищенными данными)
        """
        if df.empty:
            return False, "DataFrame пуст.", df

        required = ['load', 'freq', 'temp']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return False, f"Отсутствуют столбцы: {', '.join(missing)}", df

        df_clean = df.copy()
        errors = []
        for col in required:
            converted = DataProcessor.clean_and_convert(df_clean, col)
            invalid_mask = converted.isna()
            if invalid_mask.any():
                invalid_rows = df_clean.index[invalid_mask].tolist()
                errors.append(f"В столбце '{col}' проблемы в строках: {invalid_rows[:10]}{'...' if len(invalid_rows)>10 else ''}")
            df_clean[col] = converted

        # Удаляем строки, где все три NaN
        df_clean = df_clean.dropna(subset=required, how='all')
        # Интерполяция для небольших пропусков
        for col in required:
            if df_clean[col].isna().sum() > 0:
                df_clean[col] = df_clean[col].interpolate(method='linear', limit=5)
        # Окончательно удаляем строки с NaN
        df_clean = df_clean.dropna(subset=required)

        if df_clean.empty:
            return False, "После очистки не осталось числовых строк. Проверьте данные.", df_clean

        if errors:
            msg = "Обнаружены проблемы с данными:\n" + "\n".join(errors) + "\nПроблемные строки были удалены."
            return True, msg, df_clean
        else:
            return True, "Данные успешно проверены.", df_clean

    @staticmethod
    def process_strain_data(df: pd.DataFrame, f0: float, t0: float,
                            sensor_type: str, g_val: Optional[float] = None,
                            c_val: Optional[float] = None) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        if df.empty:
            return None, None

        # Определяем K
        if sensor_type == 'MAS‑VWS‑EM15H (встроенный)':
            K = CONFIG["DEFAULT_K_EM15H"]
        elif sensor_type == 'MAS‑VWS‑SM25H (поверхностный длинная база)':
            K = CONFIG["DEFAULT_K_SM25H"]
        elif sensor_type in ['MAS‑VWS‑SM15 (поверхностный)', 'MAS‑VWE (давление грунта)']:
            if g_val is None or c_val is None:
                return None, None
            K = g_val * c_val
        else:
            return None, None

        df = df.copy()
        df['strain'] = K * (df['freq']**2 - f0**2) + (df['temp'] - t0) * (CONFIG["F_STRING"] - CONFIG["F_CONCRETE"])
        df['stress_MPa'] = CONFIG["E_MODULUS"] * df['strain'] / 1_000_000 * 0.00689476

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

# ------------------------------------------------------------
# КЛАСС ДЛЯ ГЕНЕРАЦИИ ОТЧЁТОВ
# ------------------------------------------------------------
class ReportGenerator:
    @staticmethod
    def excel(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Результат')
            stats_df = pd.DataFrame.from_dict(stats, orient='index', columns=['Значение'])
            stats_df.to_excel(writer, sheet_name='Сводка')
            ws_spec = writer.book.add_worksheet('Спецификация датчика')
            specs_text = get_sensor_specs(sensor_type)
            row = 0
            for line in specs_text.split('\n'):
                ws_spec.write(row, 0, line)
                row += 1
        return output.getvalue()

    @staticmethod
    def pdf(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
            f0: float, t0: float) -> io.BytesIO:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from PIL import Image
        import tempfile
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(df['load'], df['strain'], 'o-', color='#1f77b4', linewidth=2, markersize=8)
        ax.set_xlabel("Нагрузка, тс")
        ax.set_ylabel("Деформация, μϵ")
        ax.set_title("Деформация от нагрузки")
        ax.grid(True)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        img = Image.open(buf)
        plt.close(fig)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        logo_path = get_resource_path("logo.png")
        if os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path)
                temp_logo = tempfile.mktemp(suffix=".png")
                logo.save(temp_logo)
                c.drawImage(temp_logo, 470, height - 80, width=60, height=30, preserveAspectRatio=True)
                os.remove(temp_logo)
            except:
                pass

        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.5, 0.5, 0.5, 0.5)
        c.drawString(50, 20, "© Геофундамент, 2026")

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, f"Отчёт по датчику: {sensor_name}")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        c.drawString(50, height - 100, f"Нулевые значения: f₀ = {f0:.1f} Гц, T₀ = {t0:.1f} °C")

        specs_text = get_sensor_specs(sensor_type)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, height - 130, "Технические характеристики датчика:")
        c.setFont("Helvetica", 9)
        y = height - 150
        for line in specs_text.split('\n'):
            if y < 50:
                c.showPage()
                y = height - 50
            c.drawString(55, y, line)
            y -= 14

        img_path = tempfile.mktemp(suffix=".png")
        img.save(img_path)
        c.drawImage(img_path, 50, height - 450, width=500, height=250)
        os.remove(img_path)

        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, height - 480, "Сводка по результатам:")
        c.setFont("Helvetica", 10)
        y = height - 500
        for key, val in stats.items():
            c.drawString(60, y, f"{key}: {val:.3f}" if isinstance(val, float) else f"{key}: {val}")
            y -= 15
            if y < 50:
                c.showPage()
                y = height - 50

        c.save()
        buffer.seek(0)
        return buffer

    @staticmethod
    def word(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
             f0: float, t0: float) -> io.BytesIO:
        from docx import Document
        from docx.shared import Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import tempfile
        import matplotlib.pyplot as plt
        from PIL import Image

        doc = Document()
        title = doc.add_heading(f"Отчёт по датчику: {sensor_name}", level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        doc.add_paragraph(f"Нулевые значения: f₀ = {f0:.1f} Гц, T₀ = {t0:.1f} °C")

        doc.add_heading("Технические характеристики датчика", level=2)
        specs_text = get_sensor_specs(sensor_type)
        for line in specs_text.split('\n'):
            doc.add_paragraph(line)

        doc.add_heading("Сводка по результатам", level=2)
        for key, val in stats.items():
            doc.add_paragraph(f"{key}: {val:.3f}" if isinstance(val, float) else f"{key}: {val}")

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(df['load'], df['strain'], 'o-', color='#1f77b4', linewidth=2, markersize=8)
        ax.set_xlabel("Нагрузка, тс")
        ax.set_ylabel("Деформация, μϵ")
        ax.set_title("Деформация от нагрузки")
        ax.grid(True)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close(fig)
        img = Image.open(buf)
        img_path = tempfile.mktemp(suffix=".png")
        img.save(img_path)
        doc.add_picture(img_path, width=Inches(6))
        os.remove(img_path)

        doc.add_heading("Таблица результатов (первые 20 строк)", level=2)
        table = doc.add_table(rows=1, cols=5)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Нагрузка, тс"
        hdr_cells[1].text = "Частота, Гц"
        hdr_cells[2].text = "Темп., °C"
        hdr_cells[3].text = "Деф., μϵ"
        hdr_cells[4].text = "Напр., МПа"
        for _, row in df.head(20).iterrows():
            row_cells = table.add_row().cells
            row_cells[0].text = f"{row['load']:.1f}"
            row_cells[1].text = f"{row['freq']:.1f}"
            row_cells[2].text = f"{row['temp']:.1f}"
            row_cells[3].text = f"{row['strain']:.1f}"
            row_cells[4].text = f"{row['stress_MPa']:.3f}"

        doc.add_paragraph("© Геофундамент, 2026").alignment = WD_ALIGN_PARAGRAPH.CENTER

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer

# ------------------------------------------------------------
# ФУНКЦИИ ДЛЯ АНАЛИЗА СТРУКТУРЫ ФАЙЛА (ОБНОВЛЕНЫ)
# ------------------------------------------------------------
def analyze_file_structure(file_bytes: bytes, file_type: str, sheet_name: str = None, delimiter: str = None) -> Dict:
    result = {
        'header_row': None,
        'data_start': 0,
        'column_names': [],
        'sample_data': None,
        'suggested_columns': {},
        'error': None,
        'available_sheets': []
    }

    try:
        if file_type == 'excel':
            xl = pd.ExcelFile(io.BytesIO(file_bytes))
            result['available_sheets'] = xl.sheet_names
            if sheet_name is None:
                sheet_name = xl.sheet_names[0] if xl.sheet_names else None
            if sheet_name is None:
                result['error'] = "В файле нет листов."
                return result

        if file_type == 'excel':
            df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, nrows=30, header=None)
        else:
            df_raw = pd.read_csv(io.BytesIO(file_bytes), nrows=30, header=None, sep=delimiter or ',', engine='python')

        keyword_rows = []
        for i, row in df_raw.iterrows():
            row_text = ' '.join([str(cell) for cell in row if pd.notna(cell)])
            row_lower = row_text.lower()
            if any(kw in row_lower for kw in ['нагрузк', 'load', 'частот', 'freq', 'температур', 'temp']):
                keyword_rows.append(i)

        if keyword_rows:
            header_row = keyword_rows[0]
            result['header_row'] = header_row
            data_start = header_row + 1
            for idx in range(data_start, min(data_start + 5, len(df_raw))):
                row = df_raw.iloc[idx]
                if all(pd.api.types.is_numeric_dtype(type(cell)) or isinstance(cell, (int, float)) for cell in row if pd.notna(cell)):
                    result['data_start'] = idx
                    break
            else:
                result['data_start'] = header_row + 1
        else:
            for i, row in df_raw.iterrows():
                if all(pd.api.types.is_numeric_dtype(type(cell)) or isinstance(cell, (int, float)) for cell in row if pd.notna(cell)):
                    result['data_start'] = i
                    break
            result['header_row'] = None

        if file_type == 'excel':
            sample = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None, skiprows=result['data_start'], nrows=20)
        else:
            sample = pd.read_csv(io.BytesIO(file_bytes), header=None, skiprows=result['data_start'], nrows=20,
                                 sep=delimiter or ',', engine='python')
        result['sample_data'] = sample

        if result['header_row'] is not None:
            if file_type == 'excel':
                header_row_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None, nrows=1, skiprows=result['header_row'])
            else:
                header_row_df = pd.read_csv(io.BytesIO(file_bytes), header=None, nrows=1, skiprows=result['header_row'],
                                            sep=delimiter or ',', engine='python')
            result['column_names'] = [str(cell).strip() for cell in header_row_df.iloc[0].tolist() if pd.notna(cell)]
        else:
            num_cols = sample.shape[1]
            result['column_names'] = [f"Колонка {i+1}" for i in range(num_cols)]

        suggested = {}
        if result['column_names']:
            for i, name in enumerate(result['column_names']):
                name_lower = name.lower()
                if re.search(r'нагрузк|load', name_lower):
                    suggested['load'] = i
                elif re.search(r'частот|freq|hz', name_lower):
                    suggested['freq'] = i
                elif re.search(r'температур|temp', name_lower):
                    suggested['temp'] = i
        result['suggested_columns'] = suggested

    except Exception as e:
        result['error'] = str(e)

    return result

# ------------------------------------------------------------
# ФУНКЦИЯ ОТОБРАЖЕНИЯ РЕЗУЛЬТАТОВ
# ------------------------------------------------------------
def display_results(result: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
                    f0: float, t0: float):
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
        excel_data = ReportGenerator.excel(result, stats, sensor_name, sensor_type)
        st.download_button(
            label="📊 Excel",
            data=excel_data,
            file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_download"
        )
    with col2:
        pdf_data = ReportGenerator.pdf(result, stats, sensor_name, sensor_type, f0, t0)
        st.download_button(
            label="📄 PDF",
            data=pdf_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            key="pdf_download"
        )
    with col3:
        word_data = ReportGenerator.word(result, stats, sensor_name, sensor_type, f0, t0)
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

# ------------------------------------------------------------
# ФУНКЦИЯ СОХРАНЕНИЯ В БД
# ------------------------------------------------------------
def save_to_db(df: pd.DataFrame, sensor_name: str) -> bool:
    try:
        conn = sqlite3.connect(CONFIG["DB_FILE"])
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

# ------------------------------------------------------------
# ПАРСИНГ СВАЙНЫХ ИСПЫТАНИЙ (заглушка)
# ------------------------------------------------------------
def parse_pile_data(file_bytes: bytes) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    # (полный код из предыдущей версии)
    return {}, ["Парсинг свайных испытаний не реализован в этой версии"]

# ------------------------------------------------------------
# ГЛАВНАЯ ФУНКЦИЯ ПРИЛОЖЕНИЯ
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
    if 'report_sensor_type' not in st.session_state:
        st.session_state.report_sensor_type = "MAS‑VWS‑EM15H (встроенный)"
    if 'report_f0' not in st.session_state:
        st.session_state.report_f0 = 1000.0
    if 'report_t0' not in st.session_state:
        st.session_state.report_t0 = 20.0
    if 'report_g_val' not in st.session_state:
        st.session_state.report_g_val = None
    if 'report_c_val' not in st.session_state:
        st.session_state.report_c_val = None
    if 'file_profile' not in st.session_state:
        st.session_state.file_profile = {}

    # Боковая панель
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

        st.markdown("---")
        with st.expander("📖 Помощь"):
            st.markdown("""
**Как пользоваться приложением:**

1. **Загрузка файла** – выберите Excel, CSV или текстовый файл.
2. **Выбор листа** – для Excel-файлов выберите нужный лист.
3. **Настройка** – укажите строку с заголовками и начало данных.
4. **Проверка данных** – нажмите "Проверить данные" для валидации.
5. **Редактирование** – при необходимости отредактируйте таблицу вручную.
6. **Обработка** – после успешной проверки нажмите "Обработать".
7. **Результаты** – скачайте отчёт в Excel, PDF или Word.
            """)

        st.markdown("---")
        st.subheader("📧 Обратная связь")
        with st.expander("Сообщить об ошибке"):
            user_name = st.text_input("Ваше имя (или ник в Telegram)", key="user_name")
            user_email = st.text_input("Ваш email", key="user_email")
            error_text = st.text_area("Опишите проблему", key="feedback_text")
            if st.button("Отправить", key="send_feedback"):
                if error_text:
                    try:
                        message = f"От: {user_name or 'Аноним'}\nEmail: {user_email or 'не указан'}\nСообщение: {error_text}"
                        if send_telegram(message):
                            st.success("✅ Спасибо! Сообщение отправлено.")
                        else:
                            st.error("❌ Не удалось отправить.")
                    except Exception as e:
                        st.error("❌ Ошибка отправки.")
                        logging.error(f"Ошибка отправки в Telegram: {e}")
                else:
                    st.warning("Напишите текст сообщения.")

    # Основные вкладки
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📂 Загрузка файла",
        "✏️ Ручной ввод",
        "🧪 Свайные испытания",
        "📋 Подбор датчиков",
        "📈 Интерактивная калибровка",
        "📊 Сравнение датчиков"
    ])

    # ---------- Вкладка 1: Загрузка файла (С УЛУЧШЕННОЙ ДИАГНОСТИКОЙ) ----------
    with tab1:
        st.subheader("Загрузите файл с данными")
        st.markdown("Поддерживаются: **Excel (.xlsx, .xls)**, **CSV (.csv)**, **текстовые файлы (.txt)**")

        uploaded_file = st.file_uploader(
            "Выберите файл",
            type=["xlsx", "xls", "csv", "txt"],
            key="file_uploader_enhanced"
        )

        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            file_type = "excel" if uploaded_file.name.endswith(('.xlsx', '.xls')) else "csv"

            delimiter = None
            if file_type == "csv":
                sample = file_bytes[:1000].decode('utf-8', errors='ignore')
                if ';' in sample and ',' not in sample:
                    delimiter = ';'
                elif ',' in sample:
                    delimiter = ','
                elif '\t' in sample:
                    delimiter = '\t'
                else:
                    delimiter = ','

            available_sheets = []
            selected_sheet = None
            if file_type == 'excel':
                try:
                    xl = pd.ExcelFile(io.BytesIO(file_bytes))
                    available_sheets = xl.sheet_names
                    if available_sheets:
                        selected_sheet = st.selectbox(
                            "Выберите лист",
                            available_sheets,
                            index=0,
                            key="sheet_selector"
                        )
                    else:
                        st.error("В файле нет листов.")
                        st.stop()
                except Exception as e:
                    st.error(f"Не удалось прочитать Excel-файл: {e}")
                    st.stop()

            with st.spinner("Анализ структуры файла..."):
                analysis = analyze_file_structure(
                    file_bytes,
                    file_type,
                    sheet_name=selected_sheet if file_type == 'excel' else None,
                    delimiter=delimiter
                )

            if analysis.get('error'):
                st.error(f"Ошибка анализа файла: {analysis['error']}")
                st.stop()

            st.success("✅ Структура файла определена")

            # Предпросмотр
            st.subheader("📋 Предпросмотр данных")
            st.caption("Ниже показаны первые 20 строк данных (после автоматического определения начала).")

            sample_df = analysis['sample_data']
            if sample_df is not None and not sample_df.empty:
                edited_df = st.data_editor(
                    sample_df,
                    num_rows="fixed",
                    use_container_width=True,
                    key="data_editor_preview",
                    column_config={
                        "_index": st.column_config.Column("Строка", disabled=True)
                    }
                )
                st.session_state['edited_data'] = edited_df
            else:
                st.warning("Не удалось показать предпросмотр данных. Возможно, файл пуст или имеет нестандартную структуру.")
                st.stop()

            # Настройка структуры
            st.subheader("🔧 Настройка структуры")
            col1, col2 = st.columns(2)
            with col1:
                header_row = st.number_input(
                    "Номер строки с заголовками (0 = нет заголовков, 1 = первая строка)",
                    min_value=0, max_value=20, value=(analysis['header_row'] + 1) if analysis['header_row'] is not None else 0,
                    step=1,
                    key="header_row_enhanced",
                    help="Укажите номер строки, которая содержит названия столбцов (1-индекс). Если заголовков нет, введите 0."
                )
            with col2:
                data_start = st.number_input(
                    "Номер строки, с которой начинаются данные (1-индекс)",
                    min_value=1, max_value=50, value=(analysis['data_start'] + 1),
                    step=1,
                    key="data_start_enhanced",
                    help="Укажите номер строки, с которой начинаются числовые данные (1-индекс)."
                )

            # Сопоставление столбцов
            st.subheader("🔗 Сопоставление столбцов")
            st.caption("Выберите, какой столбец соответствует нагрузке, частоте и температуре.")

            if analysis['column_names']:
                col_names = analysis['column_names']
            else:
                if sample_df is not None:
                    col_names = [f"Колонка {i+1}" for i in range(sample_df.shape[1])]
                else:
                    col_names = []

            if not col_names:
                st.warning("Не удалось определить имена столбцов. Пожалуйста, проверьте структуру файла или используйте ручной ввод.")
                st.stop()

            suggested = analysis['suggested_columns']
            options = ["Не выбрано"] + col_names

            load_idx = suggested.get('load', -1)
            freq_idx = suggested.get('freq', -1)
            temp_idx = suggested.get('temp', -1)

            col_load = st.selectbox(
                "Столбец с нагрузкой (load)",
                options=options,
                index=load_idx + 1 if load_idx >= 0 else 0,
                key="col_load_enhanced"
            )
            col_freq = st.selectbox(
                "Столбец с частотой (freq)",
                options=options,
                index=freq_idx + 1 if freq_idx >= 0 else 0,
                key="col_freq_enhanced"
            )
            col_temp = st.selectbox(
                "Столбец с температурой (temp)",
                options=options,
                index=temp_idx + 1 if temp_idx >= 0 else 0,
                key="col_temp_enhanced"
            )

            if col_load == "Не выбрано" or col_freq == "Не выбрано" or col_temp == "Не выбрано":
                st.warning("Пожалуйста, выберите все три столбца (нагрузка, частота, температура).")
                st.stop()

            load_col = col_names.index(col_load) if col_load in col_names else -1
            freq_col = col_names.index(col_freq) if col_freq in col_names else -1
            temp_col = col_names.index(col_temp) if col_temp in col_names else -1

            # Загрузка данных
            try:
                if file_type == 'excel':
                    if header_row == 0:
                        df_full = pd.read_excel(io.BytesIO(file_bytes), sheet_name=selected_sheet, header=None, skiprows=data_start - 1)
                    else:
                        df_full = pd.read_excel(io.BytesIO(file_bytes), sheet_name=selected_sheet, header=header_row - 1, skiprows=data_start - 1)
                else:
                    if header_row == 0:
                        df_full = pd.read_csv(io.BytesIO(file_bytes), header=None, skiprows=data_start - 1,
                                              sep=delimiter, engine='python')
                    else:
                        df_full = pd.read_csv(io.BytesIO(file_bytes), header=header_row - 1, skiprows=data_start - 1,
                                              sep=delimiter, engine='python')
            except Exception as e:
                st.error(f"Ошибка чтения файла: {e}")
                st.stop()

            if len(df_full.columns) <= max(load_col, freq_col, temp_col):
                st.error("Выбранные столбцы выходят за пределы данных. Проверьте настройки.")
                st.stop()

            df_mapped = df_full.iloc[:, [load_col, freq_col, temp_col]].copy()
            df_mapped.columns = ['load', 'freq', 'temp']

            # --- НОВЫЙ ЭТАП: ПРОВЕРКА И ВАЛИДАЦИЯ ДАННЫХ ---
            st.subheader("🔍 Проверка данных")
            if st.button("✅ Проверить данные", key="validate_data_button"):
                with st.spinner("Валидация данных..."):
                    valid, msg, df_clean = DataProcessor.validate_data(df_mapped)
                if valid:
                    st.success("✅ " + msg)
                    st.session_state['validated_df'] = df_clean
                    st.session_state['validation_passed'] = True
                else:
                    st.error("❌ " + msg)
                    st.session_state['validation_passed'] = False

            if st.session_state.get('validation_passed', False):
                st.info("Данные прошли проверку. Вы можете отредактировать их в таблице ниже перед обработкой.")
                edited_df_final = st.data_editor(
                    st.session_state['validated_df'],
                    num_rows="dynamic",
                    use_container_width=True,
                    key="data_editor_final"
                )
                st.session_state['final_df'] = edited_df_final

                st.session_state.report_sensor_type = sensor_type
                st.session_state.report_f0 = f0
                st.session_state.report_t0 = t0
                st.session_state.report_g_val = g_val
                st.session_state.report_c_val = c_val

                if st.button("🚀 Обработать данные", key="process_button_final"):
                    df_to_process = st.session_state.get('final_df', df_mapped)
                    with st.spinner("Обработка данных..."):
                        result, stats = DataProcessor.process_strain_data(
                            df_to_process, f0, t0, sensor_type, g_val, c_val
                        )
                    if result is not None:
                        st.session_state.result = result
                        st.session_state.stats = stats
                        st.session_state.sensor_name = uploaded_file.name
                        display_results(result, stats, uploaded_file.name, sensor_type, f0, t0)
                    else:
                        st.error("Ошибка обработки данных. Проверьте правильность данных.")
                        logging.error(f"Ошибка обработки файла {uploaded_file.name}")
                        send_telegram(f"Ошибка обработки файла {uploaded_file.name}")
            else:
                if 'validation_passed' in st.session_state and not st.session_state.validation_passed:
                    st.warning("Сначала исправьте ошибки в данных или загрузите другой файл.")
                else:
                    st.info("Нажмите 'Проверить данные' для валидации.")

        else:
            st.info("Загрузите файл для начала работы.")

    # ---------- Остальные вкладки (без изменений) ----------
    with tab2:
        st.subheader("✏️ Ручной ввод")
        st.info("Реализация ручного ввода (полный код из предыдущей версии)")

    with tab3:
        st.subheader("🧪 Свайные испытания")
        st.info("Реализация свайных испытаний (полный код из предыдущей версии)")

    with tab4:
        st.subheader("📋 Подбор датчиков")
        st.info("Реализация подбора датчиков (полный код из предыдущей версии)")

    with tab5:
        st.subheader("📈 Интерактивная калибровка")
        st.info("Реализация интерактивной калибровки (полный код из предыдущей версии)")

    with tab6:
        st.subheader("📊 Сравнение датчиков")
        st.info("Реализация сравнения датчиков (полный код из предыдущей версии)")

if __name__ == "__main__":
    main()
