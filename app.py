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

# ------------------------------------------------------------
# Путь к ресурсам (для .exe и для разработки)
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
# Инициализация сессии
# ------------------------------------------------------------
if 'result' not in st.session_state:
    st.session_state.result = None
if 'sensor_name' not in st.session_state:
    st.session_state.sensor_name = ""
if 'config' not in st.session_state:
    st.session_state.config = load_config()

# ------------------------------------------------------------
# Обработка данных (с приведением типов)
# ------------------------------------------------------------
def process_data(df, f0, t0, sensor_type, g_val=None, c_val=None):
    if df.empty:
        return None, None

    # Принудительно преобразуем колонки в числа
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
    elif sensor_type == 'MAS‑VWS‑SM15 (поверхностный)':
        if g_val is None or c_val is None:
            st.error("Для SM15 необходимо ввести G и C.")
            return None, None
        K = g_val * c_val
    elif sensor_type == 'MAS‑VWE (давление грунта)':
        if g_val is None or c_val is None:
            st.error("Для VWE необходимо ввести G и C.")
            return None, None
        K = g_val * c_val
    else:
        st.error("Неизвестный тип датчика.")
        return None, None

    df = df.copy()
    df['strain'] = K * (df['freq']**2 - f0**2) + (df['temp'] - t0) * (F_STRING - F_CONCRETE)
    df['stress_MPa'] = E_MODULUS * df['strain'] / 1_000_000 * 0.00689476

    # Сбор статистики
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
# Генерация отчётов (PDF, Word, Excel)
# ------------------------------------------------------------

def generate_excel_report(df, stats, sensor_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Результат')
        # Лист со сводкой
        stats_df = pd.DataFrame.from_dict(stats, orient='index', columns=['Значение'])
        stats_df.to_excel(writer, sheet_name='Сводка')
    return output.getvalue()

def generate_pdf_report(df, stats, sensor_name, f0, t0):
    # Сначала создаём график через matplotlib
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

    # Логотип
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

    # График
    img_path = tempfile.mktemp(suffix=".png")
    img.save(img_path)
    c.drawImage(img_path, 50, height - 450, width=500, height=250)
    os.remove(img_path)

    # Сводка
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

def generate_word_report(df, stats, sensor_name, f0, t0):
    doc = Document()
    # Заголовок
    title = doc.add_heading(f"Отчёт по датчику: {sensor_name}", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    doc.add_paragraph(f"Нулевые значения: f₀ = {f0:.1f} Гц, T₀ = {t0:.1f} °C")

    # Сводка
    doc.add_heading("Сводка по результатам", level=2)
    for key, val in stats.items():
        doc.add_paragraph(f"{key}: {val:.3f}" if isinstance(val, float) else f"{key}: {val}")

    # График
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

    # Таблица результатов (первые 20 строк)
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

    # Подпись
    doc.add_paragraph("© Геофундамент, 2026").alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ------------------------------------------------------------
# Отображение результатов (график, таблица, скачивание)
# ------------------------------------------------------------
def display_results(result, stats, sensor_name, f0, t0):
    st.subheader("✅ Результат обработки")
    st.dataframe(result)

    # График
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

    # Скачивание
    st.subheader("📥 Скачать отчёт")
    col1, col2, col3 = st.columns(3)
    with col1:
        excel_data = generate_excel_report(result, stats, sensor_name)
        st.download_button(
            label="📊 Excel",
            data=excel_data,
            file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        pdf_data = generate_pdf_report(result, stats, sensor_name, f0, t0)
        st.download_button(
            label="📄 PDF",
            data=pdf_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf"
        )
    with col3:
        word_data = generate_word_report(result, stats, sensor_name, f0, t0)
        st.download_button(
            label="📝 Word",
            data=word_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

# ------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------
st.set_page_config(page_title="Анализ датчиков", layout="wide")
st.title("📊 Обработка данных тензодатчиков")

# Боковая панель с настройками (общая для обеих вкладок)
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
    g_val = None
    c_val = None
    if sensor_type in ["MAS‑VWS‑SM15 (поверхностный)", "MAS‑VWE (давление грунта)"]:
        st.subheader("Калибровочные коэффициенты")
        g_val = st.number_input("G", value=1.0, step=0.001, format="%.3f", key="g_val")
        c_val = st.number_input("C", value=1.0, step=0.001, format="%.3f", key="c_val")
        st.caption("Из сертификата датчика.")

    st.header("Нулевые значения")
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

# ------------------------------------------------------------
# Вкладки
# ------------------------------------------------------------
tab1, tab2 = st.tabs(["📂 Загрузка файла", "✏️ Ручной ввод"])

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

            # Автоопределение столбцов
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

            with st.spinner("Обработка данных..."):
                result, stats = process_data(df_mapped, f0, t0, sensor_type, g_val, c_val)

            if result is not None:
                st.session_state.result = result
                st.session_state.sensor_name = uploaded_file.name
                display_results(result, stats, uploaded_file.name, f0, t0)

        except Exception as e:
            st.error(f"Ошибка при обработке: {e}")

# ---------- Вкладка 2: Ручной ввод ----------
with tab2:
    st.subheader("Вставьте данные из буфера обмена")
    st.markdown("""
    Вставьте данные в текстовое поле. Ожидается **три колонки** в порядке:
    1. Нагрузка (тс)
    2. Частота (Гц)
    3. Температура (°C)

    Разделитель можно выбрать ниже. Пример (табуляция):

