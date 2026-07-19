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

# ------------------------------------------------------------
# Путь к ресурсам (работает в .exe и в обычном режиме)
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
# Функция обработки данных
# ------------------------------------------------------------
def process_data(df, f0, t0, sensor_type, g_val=None, c_val=None):
    if df.empty:
        return None

    if sensor_type == 'MAS‑VWS‑EM15H (встроенный)':
        K = DEFAULT_K_EM15H
    elif sensor_type == 'MAS‑VWS‑SM25H (поверхностный длинная база)':
        K = DEFAULT_K_SM25H
    elif sensor_type == 'MAS‑VWS‑SM15 (поверхностный)':
        if g_val is None or c_val is None:
            st.error("Для SM15 необходимо ввести G и C.")
            return None
        K = g_val * c_val
    elif sensor_type == 'MAS‑VWE (давление грунта)':
        if g_val is None or c_val is None:
            st.error("Для VWE необходимо ввести G и C.")
            return None
        K = g_val * c_val
    else:
        st.error("Неизвестный тип датчика.")
        return None

    df = df.copy()
    df['strain'] = K * (df['freq']**2 - f0**2) + (df['temp'] - t0) * (F_STRING - F_CONCRETE)
    df['stress_MPa'] = E_MODULUS * df['strain'] / 1_000_000 * 0.00689476
    return df

# ------------------------------------------------------------
# Генерация PDF-отчёта
# ------------------------------------------------------------
def generate_pdf_report(df, sensor_name, f0, t0):
    try:
        import plotly.io as pio
        pio.kaleido.scope.default_format = "png"
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['load'], y=df['strain'], mode='lines+markers', name='Деформация, μϵ'))
        fig.update_layout(title="Деформация от нагрузки", xaxis_title="Нагрузка, тс", yaxis_title="Деформация, μϵ")
        img_bytes = fig.to_image(format="png", width=800, height=400)
        img = Image.open(io.BytesIO(img_bytes))
    except:
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

    img_path = tempfile.mktemp(suffix=".png")
    img.save(img_path)
    c.drawImage(img_path, 50, height - 450, width=500, height=250)
    os.remove(img_path)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 480, "Таблица результатов (первые 20 строк):")
    c.setFont("Helvetica", 10)
    y = height - 500
    headers = ["Нагрузка, тс", "Частота, Гц", "Темп., °C", "Деф., μϵ", "Напр., МПа"]
    c.drawString(50, y, headers[0])
    c.drawString(120, y, headers[1])
    c.drawString(200, y, headers[2])
    c.drawString(280, y, headers[3])
    c.drawString(370, y, headers[4])
    y -= 15
    for _, row in df.head(20).iterrows():
        c.drawString(50, y, f"{row['load']:.1f}")
        c.drawString(120, y, f"{row['freq']:.1f}")
        c.drawString(200, y, f"{row['temp']:.1f}")
        c.drawString(280, y, f"{row['strain']:.1f}")
        c.drawString(370, y, f"{row['stress_MPa']:.3f}")
        y -= 15
        if y < 50:
            c.showPage()
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
            y = height - 50

    c.save()
    buffer.seek(0)
    return buffer

# ------------------------------------------------------------
# Интерфейс Streamlit
# ------------------------------------------------------------
st.set_page_config(page_title="Анализ датчиков", layout="wide")
st.title("📊 Обработка данных тензодатчиков")

# Боковая панель
with st.sidebar:
    st.header("Настройки")
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

    # Логотип
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

# Основная вкладка загрузки
st.subheader("📂 Загрузите файл Excel с данными")
uploaded_file = st.file_uploader("Выберите файл .xlsx или .xls", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df_raw = pd.read_excel(uploaded_file)
        st.success("Файл успешно загружен!")
        st.dataframe(df_raw.head())

        # Проверяем наличие столбцов load, freq, temp
        required = ['load', 'freq', 'temp']
        missing = [col for col in required if col not in df_raw.columns]
        if missing:
            st.error(f"В файле отсутствуют столбцы: {', '.join(missing)}. Пожалуйста, переименуйте их или добавьте.")
            st.stop()

        df = df_raw[required].copy().dropna()
        if df.empty:
            st.warning("После удаления пустых строк данных не осталось.")
            st.stop()

        # Обработка
        with st.spinner("Обработка данных..."):
            result = process_data(df, f0, t0, sensor_type, g_val, c_val)

        if result is not None:
            st.session_state.result = result
            st.session_state.sensor_name = uploaded_file.name

            st.subheader("✅ Результат обработки")
            st.dataframe(result)

            # График
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=result['load'], y=result['strain'], mode='lines+markers', name='Деформация, μϵ'))
            fig.update_layout(
                title="Деформация от нагрузки",
                xaxis_title="Нагрузка, тс",
                yaxis_title="Деформация, μϵ"
            )
            # Водяной знак
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

            # Кнопки скачивания
            col1, col2 = st.columns(2)
            with col1:
                # Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result.to_excel(writer, index=False, sheet_name='Результат')
                st.download_button(
                    label="📥 Скачать результат (Excel)",
                    data=output.getvalue(),
                    file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            with col2:
                # PDF
                pdf_buffer = generate_pdf_report(result, uploaded_file.name, f0, t0)
                st.download_button(
                    label="📄 Скачать отчёт (PDF)",
                    data=pdf_buffer.getvalue(),
                    file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )
    except Exception as e:
        st.error(f"Ошибка при обработке: {e}")
else:
    st.info("👆 Загрузите Excel-файл для начала работы.")
