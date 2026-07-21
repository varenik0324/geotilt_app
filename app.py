import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import io
import json
import os
import sys
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image
import tempfile
import base64
import re
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import logging
import sqlite3

# ========== ЛОГГИРОВАНИЕ ==========
logging.basicConfig(filename='app_errors.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ========== ПРОВЕРКА ОБНОВЛЕНИЙ ==========
def check_for_updates():
    try:
        import requests
        url = "https://your-server.com/version.txt"  # ЗАМЕНИТЕ НА РЕАЛЬНЫЙ URL
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            latest_version = r.text.strip()
            current_version = "1.0"
            if latest_version != current_version:
                st.warning(f"Доступна новая версия {latest_version}! Пожалуйста, обновитесь.")
    except:
        pass  # если нет интернета или файл недоступен, просто игнорируем

# ------------------------------------------------------------
# Путь к ресурсам
# ------------------------------------------------------------
def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# ------------------------------------------------------------
# Константы
# ------------------------------------------------------------
DEFAULT_K_EM15H = 0.0031559
DEFAULT_K_SM25H = 0.0035708
F_STRING = 12.2
F_CONCRETE = 10.0
E_MODULUS = 3_000_000

CONFIG_FILE = get_resource_path("app_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(config):
    if getattr(sys, 'frozen', False):
        config_dir = os.path.dirname(sys.executable)
        config_path = os.path.join(config_dir, "app_config.json")
    else:
        config_path = CONFIG_FILE
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ------------------------------------------------------------
# ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ ДАТЧИКОВ
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

def get_sensor_specs(sensor_type):
    """Возвращает форматированный текст с характеристиками датчика."""
    specs = SENSOR_SPECS.get(sensor_type)
    if not specs:
        return "Характеристики для данного типа датчика не найдены."
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
# Инициализация сессии (без конфликтов с виджетами)
# ------------------------------------------------------------
if 'result' not in st.session_state:
    st.session_state.result = None
if 'stats' not in st.session_state:
    st.session_state.stats = None
if 'sensor_name' not in st.session_state:
    st.session_state.sensor_name = ""
if 'config' not in st.session_state:
    st.session_state.config = load_config()

# Переменные для отчётов (сохраняются при обработке)
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

# ------------------------------------------------------------
# Обработка тензодатчиков
# ------------------------------------------------------------
def process_data(df, f0, t0, sensor_type, g_val=None, c_val=None):
    if df.empty:
        return None, None

    for col in ['load', 'freq', 'temp']:
        df[col] = df[col].astype(str).str.replace(',', '.').str.replace(' ', '')
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna()
    if df.empty:
        st.error("После очистки данных не осталось числовых строк.")
        return None, None

    if sensor_type == 'MAS‑VWS‑EM15H (встроенный)':
        K = DEFAULT_K_EM15H
    elif sensor_type == 'MAS‑VWS‑SM25H (поверхностный длинная база)':
        K = DEFAULT_K_SM25H
    elif sensor_type in ['MAS‑VWS‑SM15 (поверхностный)', 'MAS‑VWE (давление грунта)']:
        if g_val is None or c_val is None:
            st.error("Для этого типа датчика требуются G и C.")
            return None, None
        K = g_val * c_val
    else:
        st.error("Неизвестный тип датчика.")
        return None, None

    df = df.copy()
    df['strain'] = K * (df['freq']**2 - f0**2) + (df['temp'] - t0) * (F_STRING - F_CONCRETE)
    df['stress_MPa'] = E_MODULUS * df['strain'] / 1_000_000 * 0.00689476

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
# Генерация отчётов (используют report_* параметры из сессии)
# ------------------------------------------------------------
def generate_excel_report(df, stats, sensor_name):
    sensor_type = st.session_state.report_sensor_type
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

def generate_pdf_report(df, stats, sensor_name):
    sensor_type = st.session_state.report_sensor_type
    f0 = st.session_state.report_f0
    t0 = st.session_state.report_t0

    fig_mpl, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df['load'], df['strain'], 'o-', color='#1f77b4', linewidth=2, markersize=8)
    ax.set_xlabel("Нагрузка, тс")
    ax.set_ylabel("Деформация, μϵ")
    ax.set_title("Деформация от нагрузки")
    ax.grid(True)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    img = Image.open(buf)
    plt.close(fig_mpl)

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

    # Спецификация
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

def generate_word_report(df, stats, sensor_name):
    sensor_type = st.session_state.report_sensor_type
    f0 = st.session_state.report_f0
    t0 = st.session_state.report_t0

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

    fig_mpl, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df['load'], df['strain'], 'o-', color='#1f77b4', linewidth=2, markersize=8)
    ax.set_xlabel("Нагрузка, тс")
    ax.set_ylabel("Деформация, μϵ")
    ax.set_title("Деформация от нагрузки")
    ax.grid(True)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig_mpl)
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

# ========== СОХРАНЕНИЕ В БАЗУ ДАННЫХ ==========
def save_to_db(df, sensor_name):
    try:
        conn = sqlite3.connect('measurements.db')
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
# Отображение результатов
# ------------------------------------------------------------
def display_results(result, stats, sensor_name):
    st.subheader("✅ Результат обработки")
    st.dataframe(result)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result['load'], y=result['strain'], mode='lines+markers', name='Деформация, μϵ'))
    fig.update_layout(
        title="Деформация от нагрузки",
        xaxis_title="Нагрузка, тс",
        yaxis_title="Деформация, μϵ",
        template="plotly_white"
    )
    logo_path = get_resource_path("logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_base64 = base64.b64encode(f.read()).decode()
        fig.add_layout_image(
            dict(
                source=f"data:image/png;base64,{logo_base64}",
                x=0.95, y=0.95,
                xref="paper", yref="paper",
                sizex=0.15, sizey=0.15,
                opacity=0.6
            )
        )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📥 Скачать отчёт")
    col1, col2, col3 = st.columns(3)
    with col1:
        excel_data = generate_excel_report(result, stats, sensor_name)
        st.download_button(
            label="📊 Excel",
            data=excel_data,
            file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_excel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    with col2:
        pdf_data = generate_pdf_report(result, stats, sensor_name)
        st.download_button(
            label="📄 PDF",
            data=pdf_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            key=f"download_pdf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    with col3:
        word_data = generate_word_report(result, stats, sensor_name)
        st.download_button(
            label="📝 Word",
            data=word_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=f"download_word_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

    # ---------- КНОПКА СОХРАНЕНИЯ В БАЗУ ----------
    st.subheader("💾 Сохранить в базу данных")
    if st.button("Сохранить текущий результат в базу"):
        if save_to_db(result, sensor_name):
            st.success("Данные сохранены в базу!")
        else:
            st.error("Ошибка сохранения в базу. Проверьте логи.")

# ------------------------------------------------------------
# ПАРСИНГ СВАЙНЫХ ИСПЫТАНИЙ (без изменений)
# ------------------------------------------------------------
PILE_A = 6.51e-08
PILE_B = -0.02931
PILE_C = 248.4372
PILE_K = -0.036375
PILE_T_REF = 23.9

def parse_pile_data(file_bytes):
    debug = []
    xl = pd.ExcelFile(file_bytes)
    sheet_names = xl.sheet_names
    debug.append(f"📋 Найдены листы: {sheet_names}")

    zero_sheet = None
    for name in sheet_names:
        if 'свая' in name.lower() and not 'испытания' in name.lower():
            zero_sheet = name
            break
    if zero_sheet is None:
        for name in sheet_names:
            df_sample = pd.read_excel(file_bytes, sheet_name=name, header=None, nrows=20)
            for idx, row in df_sample.iterrows():
                if any('Частота' in str(cell) for cell in row) and any('Температура' in str(cell) for cell in row):
                    zero_sheet = name
                    break
            if zero_sheet:
                break
    debug.append(f"🔍 Нулевой лист: {zero_sheet}")

    test_sheet = None
    for name in sheet_names:
        if 'испытания' in name.lower() or 'испыт' in name.lower():
            test_sheet = name
            break
    if test_sheet is None:
        for name in sheet_names:
            df_sample = pd.read_excel(file_bytes, sheet_name=name, header=None, nrows=20)
            for idx, row in df_sample.iterrows():
                if any('Нагрузка' in str(cell) for cell in row) and any('Давление' in str(cell) for cell in row):
                    test_sheet = name
                    break
            if test_sheet:
                break
    debug.append(f"🔍 Лист испытаний: {test_sheet}")

    if zero_sheet is None or test_sheet is None:
        raise ValueError(f"Не найдены оба листа. zero={zero_sheet}, test={test_sheet}")

    df_zero = pd.read_excel(file_bytes, sheet_name=zero_sheet, header=None)
    zero_data = {}

    start_row = None
    freq_col, temp_col = None, None
    for idx, row in df_zero.iterrows():
        row_str = ' '.join(str(cell) for cell in row if pd.notna(cell))
        if 'Частота' in row_str and 'Температура' in row_str:
            for i, cell in enumerate(row):
                if isinstance(cell, str):
                    if 'Частота' in cell:
                        freq_col = i
                    if 'Температура' in cell:
                        temp_col = i
            start_row = idx + 1
            break

    if start_row is None:
        for idx, row in df_zero.iterrows():
            first = str(row[0]).strip()
            if first and re.search(r'\d\s*[й]?\s*(верх|сред|низ)', first, re.IGNORECASE):
                start_row = idx
                for i in range(1, len(row)):
                    if pd.notna(row[i]) and isinstance(row[i], (int, float)):
                        if freq_col is None:
                            freq_col = i
                        elif temp_col is None:
                            temp_col = i
                            break
                break
    if start_row is None:
        start_row = 0
    if freq_col is None:
        freq_col = 1
    if temp_col is None:
        temp_col = 2

    debug.append(f"📌 Нулевые: start_row={start_row}, freq_col={freq_col}, temp_col={temp_col}")

    for idx in range(start_row, len(df_zero)):
        row = df_zero.iloc[idx]
        first_cell = str(row[0]).strip()
        if not first_cell or 'уровень' in first_cell.lower():
            continue
        try:
            freq_val = float(row[freq_col]) if pd.notna(row[freq_col]) else None
            temp_val = float(row[temp_col]) if pd.notna(row[temp_col]) else None
        except:
            continue
        if freq_val is not None and temp_val is not None:
            sensor_name = first_cell
            zero_data[sensor_name] = {'f0': freq_val, 'T0': temp_val}

    debug.append(f"📈 Найдено нулевых записей: {len(zero_data)}")
    if zero_data:
        debug.append(f"Примеры: {list(zero_data.keys())[:3]}")

    df_test = pd.read_excel(file_bytes, sheet_name=test_sheet, header=None)

    header_row = None
    for idx, row in df_test.iterrows():
        row_str = ' '.join(str(cell) for cell in row if pd.notna(cell))
        if ('Время' in row_str and 'Нагрузка' in row_str and 'Давление' in row_str) or \
           ('время' in row_str.lower() and 'нагрузка' in row_str.lower() and 'давление' in row_str.lower()):
            header_row = idx
            break
    debug.append(f"📌 Строка заголовков испытаний: {header_row}")

    if header_row is None:
        raise ValueError("Не удалось найти заголовки в листе испытаний.")

    headers = df_test.iloc[header_row].tolist()
    headers = [str(h).strip() if pd.notna(h) else '' for h in headers]

    step_columns = {}
    current_step = None
    for i, h in enumerate(headers):
        if 'Ступень' in h:
            match = re.search(r'Ступень\s*(\d+)', h)
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
        debug.append("⚠️ Ступени не обнаружены, создаём одну группу")
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

    debug.append(f"🧩 Найдено ступеней: {len(step_columns)}")

    sensor_rows = []
    for idx in range(header_row + 1, len(df_test)):
        row = df_test.iloc[idx]
        first_cell = str(row[0]).strip()
        if first_cell and re.search(r'\d\s*[й]?\s*(верх|сред|низ)', first_cell, re.IGNORECASE):
            sensor_rows.append(idx)
            continue
        if first_cell and re.match(r'^\d+$', first_cell):
            sensor_rows.append(idx)

    debug.append(f"🔎 Найдено строк датчиков: {len(sensor_rows)}")
    if sensor_rows:
        debug.append(f"Примеры: {[str(df_test.iloc[i,0]).strip() for i in sensor_rows[:3]]}")

    results = {}
    for idx in sensor_rows:
        sensor_name = str(df_test.iloc[idx, 0]).strip()
        rows = []
        for step, cols in step_columns.items():
            if 'Время' not in cols or 'Нагрузка' not in cols or 'Давление' not in cols:
                continue
            row_data = df_test.iloc[idx]
            time_val = row_data[cols['Время']] if cols.get('Время') is not None else None
            load_val = row_data[cols['Нагрузка']] if cols.get('Нагрузка') is not None else None
            press_val = row_data[cols['Давление']] if cols.get('Давление') is not None else None
            freq_val = row_data[cols.get('Частота')] if cols.get('Частота') is not None else None
            temp_val = row_data[cols.get('Температура')] if cols.get('Температура') is not None else None
            rows.append({
                'Время': time_val,
                'Нагрузка, тс': load_val,
                'Давление, бар': press_val,
                'Частота, Гц': freq_val,
                'Температура, °С': temp_val,
                'Ступень': step
            })
        if rows:
            df_sensor = pd.DataFrame(rows)
            if sensor_name in zero_data:
                f0 = zero_data[sensor_name]['f0']
                T0 = zero_data[sensor_name]['T0']
                df_sensor['Давление_расч, Psi'] = np.nan
                df_sensor['Давление_расч, МПа'] = np.nan
                for i, row in df_sensor.iterrows():
                    f = row['Частота, Гц']
                    T = row['Температура, °С']
                    if pd.notna(f) and pd.notna(T):
                        Psi = PILE_A * (f**2) + PILE_B * f + PILE_C + PILE_K * (T - PILE_T_REF)
                        df_sensor.at[i, 'Давление_расч, Psi'] = Psi
                        df_sensor.at[i, 'Давление_расч, МПа'] = Psi * 0.00689475729317831
                results[sensor_name] = df_sensor
            else:
                results[sensor_name] = df_sensor

    return results, debug

# ------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------
st.set_page_config(page_title="Анализ датчиков", layout="wide")
st.title("📊 Обработка данных тензодатчиков")

# Проверка обновлений
check_for_updates()

# Боковая панель
with st.sidebar:
    st.header("Настройки датчика")
    sensor_type = st.selectbox(
        "Тип датчика",
        [
            "MAS‑VWS‑EM15H (встроенный)",
            "MAS‑VWS‑SM15 (поверхностный)",
            "MAS‑VWS‑SM25H (поверхностный длинная база)",
            "MAS‑VWE (давление грунта)"
        ],
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

    if st.button("Сохранить настройки"):
        config = st.session_state.config
        config['sensor_type'] = sensor_type
        config['f0'] = f0
        config['t0'] = t0
        if g_val is not None and c_val is not None:
            config['g_val'] = g_val
            config['c_val'] = c_val
        save_config(config)
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

    # ---------- ДОКУМЕНТАЦИЯ ----------
    st.markdown("---")
    with st.expander("📖 Помощь"):
        st.markdown("""
**Как пользоваться приложением:**

1. **Загрузка файла** – выберите Excel-файл с колонками: нагрузка, частота, температура.
2. **Ручной ввод** – вставьте данные из буфера обмена.
3. **Свайные испытания** – загрузите файл с листами "Свая..." и "Испытания".
4. **Настройки** – выберите тип датчика, укажите f₀ и T₀.
5. **Результаты** – вы можете скачать отчёт в Excel, PDF или Word.

**Форматы файлов:** .xlsx, .xls
        """)

    # ---------- ОБРАТНАЯ СВЯЗЬ ----------
    st.markdown("---")
    st.subheader("📧 Обратная связь")
    with st.expander("Сообщить об ошибке"):
        error_text = st.text_area("Опишите проблему")
        if st.button("Отправить"):
            if error_text:
                logging.error(f"Сообщение пользователя: {error_text}")
                st.success("Спасибо! Мы получили ваше сообщение.")

# ------------------------------------------------------------
# Вкладки
# ------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📂 Загрузка файла", "✏️ Ручной ввод", "🧪 Свайные испытания"])

# ---------- Вкладка 1: Загрузка файла ----------
with tab1:
    st.subheader("Загрузите файл Excel с данными")
    uploaded_file = st.file_uploader("Выберите файл .xlsx или .xls", type=["xlsx", "xls"], key="file_uploader")

    if uploaded_file is not None:
        try:
            df_raw = pd.read_excel(uploaded_file)
            st.success("Файл успешно загружен!")
            df_raw.columns = [str(col) for col in df_raw.columns]
            st.write("Исходные столбцы:", df_raw.columns.tolist())
            st.dataframe(df_raw.head())

            col_map = {}
            for col in df_raw.columns:
                col_lower = col.lower()
                if re.search(r'нагрузк|load', col_lower):
                    col_map[col] = 'load'
                elif re.search(r'частот|freq|hz', col_lower):
                    col_map[col] = 'freq'
                elif re.search(r'температур|temp', col_lower):
                    col_map[col] = 'temp'

            default_load = next((c for c in col_map if col_map[c] == 'load'), None)
            default_freq = next((c for c in col_map if col_map[c] == 'freq'), None)
            default_temp = next((c for c in col_map if col_map[c] == 'temp'), None)

            st.subheader("🔧 Сопоставление столбцов")
            col_load = st.selectbox("Выберите столбец с нагрузкой (load)", options=[None] + df_raw.columns.tolist(), index=0 if default_load is None else df_raw.columns.tolist().index(default_load)+1, key="col_load")
            col_freq = st.selectbox("Выберите столбец с частотой (freq)", options=[None] + df_raw.columns.tolist(), index=0 if default_freq is None else df_raw.columns.tolist().index(default_freq)+1, key="col_freq")
            col_temp = st.selectbox("Выберите столбец с температурой (temp)", options=[None] + df_raw.columns.tolist(), index=0 if default_temp is None else df_raw.columns.tolist().index(default_temp)+1, key="col_temp")

            if col_load is None or col_freq is None or col_temp is None:
                st.warning("Пожалуйста, выберите все три столбца.")
                st.stop()

            df_mapped = df_raw[[col_load, col_freq, col_temp]].copy()
            df_mapped.columns = ['load', 'freq', 'temp']

            st.session_state.report_sensor_type = sensor_type
            st.session_state.report_f0 = f0
            st.session_state.report_t0 = t0
            st.session_state.report_g_val = g_val
            st.session_state.report_c_val = c_val

            with st.spinner("Обработка данных..."):
                result, stats = process_data(df_mapped, f0, t0, sensor_type, g_val, c_val)

            if result is not None:
                st.session_state.result = result
                st.session_state.stats = stats
                st.session_state.sensor_name = uploaded_file.name
                display_results(result, stats, uploaded_file.name)

        except Exception as e:
            st.error(f"Ошибка при обработке: {e}")
            logging.error(f"Ошибка: {e}, файл: {uploaded_file.name if uploaded_file else 'ручной ввод'}")

# ---------- Вкладка 2: Ручной ввод ----------
with tab2:
    st.subheader("Вставьте данные из буфера обмена")
    st.markdown(
        "Вставьте данные в текстовое поле. Ожидается **три колонки** в порядке:\n"
        "1. Нагрузка (тс)\n"
        "2. Частота (Гц)\n"
        "3. Температура (°C)\n\n"
        "Разделитель можно выбрать ниже. Пример (табуляция):\n"
        "0.0  1000.0  20.0\n"
        "5.0  1012.5  21.2\n"
        "10.0 1025.0  22.0"
    )

    delimiter = st.selectbox(
        "Разделитель",
        options=["\\t (табуляция)", ", (запятая)", "; (точка с запятой)", "пробел"],
        index=0,
        key="delimiter"
    )
    if delimiter == "\\t (табуляция)":
        sep = '\t'
    elif delimiter == ", (запятая)":
        sep = ','
    elif delimiter == "; (точка с запятой)":
        sep = ';'
    else:
        sep = ' '

    text_data = st.text_area("Введите или вставьте данные", height=200, key="manual_input")

    if st.button("Обработать введённые данные", key="process_manual"):
        if not text_data.strip():
            st.warning("Пожалуйста, введите данные.")
        else:
            try:
                lines = text_data.strip().splitlines()
                rows = []
                for line in lines:
                    if line.strip():
                        parts = line.split(sep)
                        parts = [p for p in parts if p.strip()]
                        if len(parts) >= 3:
                            rows.append(parts[:3])
                if not rows:
                    st.error("Не удалось распознать данные. Проверьте формат и разделитель.")
                else:
                    df_manual = pd.DataFrame(rows, columns=['load', 'freq', 'temp'])

                    st.session_state.report_sensor_type = sensor_type
                    st.session_state.report_f0 = f0
                    st.session_state.report_t0 = t0
                    st.session_state.report_g_val = g_val
                    st.session_state.report_c_val = c_val

                    with st.spinner("Обработка данных..."):
                        result, stats = process_data(df_manual, f0, t0, sensor_type, g_val, c_val)

                    if result is not None:
                        st.session_state.result = result
                        st.session_state.stats = stats
                        st.session_state.sensor_name = "Ручной ввод"
                        display_results(result, stats, "Ручной ввод")

            except Exception as e:
                st.error(f"Ошибка при обработке: {e}")
                logging.error(f"Ошибка ручного ввода: {e}")

# ---------- Вкладка 3: Свайные испытания ----------
with tab3:
    st.subheader("📂 Загрузите файл с данными испытаний свай")
    st.markdown("Файл будет автоматически распознан. Поддерживаются любые структуры с нулевыми значениями и испытаниями.")
    uploaded_pile = st.file_uploader("Выберите файл .xlsx", type=["xlsx"], key="pile_uploader")

    if uploaded_pile is not None:
        try:
            with st.spinner("Парсинг и обработка данных..."):
                results, debug_msgs = parse_pile_data(uploaded_pile)

            with st.expander("🔍 Отладка парсинга", expanded=True):
                for msg in debug_msgs:
                    st.info(msg)

            st.success(f"✅ Обработано датчиков: {len(results)}")

            if not results:
                st.warning("Датчики не найдены. Проверьте структуру файла и отладочные сообщения.")
            else:
                for sensor_name, df in results.items():
                    with st.expander(f"📊 Датчик: {sensor_name}", expanded=True):
                        st.dataframe(df)

                        if 'Нагрузка, тс' in df.columns:
                            if 'Давление, бар' in df.columns:
                                press_bar = df.dropna(subset=['Нагрузка, тс', 'Давление, бар'])
                                if not press_bar.empty:
                                    press_bar['Давление_бар_МПа'] = press_bar['Давление, бар'] * 0.1
                                    fig = go.Figure()
                                    fig.add_trace(go.Scatter(x=press_bar['Нагрузка, тс'], y=press_bar['Давление_бар_МПа'],
                                                             mode='lines+markers', name='Давление (из файла) МПа'))
                            if 'Давление_расч, МПа' in df.columns:
                                plot_df = df.dropna(subset=['Нагрузка, тс', 'Давление_расч, МПа'])
                                if not plot_df.empty:
                                    if 'fig' not in locals():
                                        fig = go.Figure()
                                    fig.add_trace(go.Scatter(x=plot_df['Нагрузка, тс'], y=plot_df['Давление_расч, МПа'],
                                                             mode='lines+markers', name='Давление (расч.) МПа'))
                            if 'fig' in locals():
                                fig.update_layout(
                                    title=f"Зависимость давления от нагрузки ({sensor_name})",
                                    xaxis_title="Нагрузка, тс",
                                    yaxis_title="Давление, МПа",
                                    template="plotly_white"
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("Нет данных для построения графика (нет давления).")

                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label=f"📥 Скачать CSV для {sensor_name}",
                            data=csv,
                            file_name=f"{sensor_name}.csv",
                            mime="text/csv",
                            key=f"download_csv_{sensor_name}"
                        )

        except Exception as e:
            st.error(f"Ошибка обработки: {e}")
            logging.error(f"Ошибка обработки свайных данных: {e}")
