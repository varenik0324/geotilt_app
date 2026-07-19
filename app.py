import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import io
import re
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
# Функция для получения правильного пути к ресурсам
# (работает как в режиме разработки, так и в собранном .exe)
# ------------------------------------------------------------
def get_resource_path(relative_path):
    """Возвращает абсолютный путь к файлу, учитывая сборку PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Запущено из .exe
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
    # Сохраняем конфиг в ту же папку, где находится .exe (или рядом с ним)
    # В режиме frozen CONFIG_FILE может указывать на временную папку, поэтому сохраняем в рабочую директорию
    if getattr(sys, 'frozen', False):
        # Сохраняем рядом с .exe
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
if 'auto_selected' not in st.session_state:
    st.session_state.auto_selected = {}

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
# Автоопределение столбцов (без изменений)
# ------------------------------------------------------------
def auto_detect_columns(df, skip_rows=0):
    # ... (код остаётся тем же, что и у вас)
    # Для краткости я не копирую его полностью, но вы вставляете свою функцию
    # В финальном файле она должна быть здесь
    pass  # Замените на ваш код

# ------------------------------------------------------------
# Генерация PDF-отчёта (с поддержкой kaleido или matplotlib)
# ------------------------------------------------------------
def generate_pdf_report(df, sensor_name, f0, t0):
    # Пытаемся использовать kaleido, если есть
    try:
        import plotly.io as pio
        pio.kaleido.scope.default_format = "png"
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['load'], y=df['strain'], mode='lines+markers', name='Деформация, μϵ'))
        fig.update_layout(title="Деформация от нагрузки", xaxis_title="Нагрузка, тс", yaxis_title="Деформация, μϵ")
        img_bytes = fig.to_image(format="png", width=800, height=400)
        img = Image.open(io.BytesIO(img_bytes))
    except:
        # Если kaleido не установлен, используем matplotlib
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

    # Подпись
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
            # повтор логотипа и подписи на новой странице
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
        key="sensor_type_select"
    )
    g_val = None
    c_val = None
    if sensor_type in ["MAS‑VWS‑SM15 (поверхностный)", "MAS‑VWE (давление грунта)"]:
        st.subheader("Калибровочные коэффициенты")
        g_val = st.number_input("G", value=1.0, step=0.001, format="%.3f", key="g_val")
        c_val = st.number_input("C", value=1.0, step=0.001, format="%.3f", key="c_val")
        st.caption("Из сертификата датчика.")

    if st.button("Сохранить настройки типа датчика"):
        config = st.session_state.config
        config['sensor_type'] = sensor_type
        if g_val is not None and c_val is not None:
            config['g_val'] = g_val
            config['c_val'] = c_val
        save_config(config)
        st.success("Настройки типа датчика сохранены!")

    # Логотип в боковой панели
    logo_path = get_resource_path("logo.png")
    if os.path.exists(logo_path):
        try:
            st.sidebar.image(logo_path, width=150)
        except:
            st.sidebar.warning("Не удалось загрузить логотип")
    else:
        st.sidebar.warning("Логотип не найден (файл logo.png)")

    st.sidebar.markdown("### 🏗️ Геофундамент")
    st.sidebar.caption("© 2026, все права защищены")

# Вкладки (ваш код без изменений)
tab1, tab2 = st.tabs(["📁 Загрузка Excel", "✏️ Ручной ввод"])

# ... (дальше идёт ваш код для tab1 и tab2, он остаётся без изменений)
# Важно: в вашем коде везде, где вы используете "logo.png", замените на get_resource_path("logo.png")
# Например, при добавлении водяного знака на график:
# if os.path.exists(get_resource_path("logo.png")):
#    with open(get_resource_path("logo.png"), "rb") as f:
#        ...

# ВНИМАНИЕ: в вашем коде есть несколько мест, где вы обращаетесь к "logo.png".
# Замените их все на get_resource_path("logo.png").

# Я покажу только изменённый фрагмент с водяным знаком:
# В разделе отображения результатов замените:
if st.session_state.result is not None:
    df = st.session_state.result
    name = st.session_state.sensor_name

    # ... (код графика) ...
    # Водяной знак
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

    # ... остальной код ...

# Остальную часть кода (вкладки, обработка) вы копируете из своего файла без изменений,
# но везде, где есть "logo.png", замените на get_resource_path("logo.png").
