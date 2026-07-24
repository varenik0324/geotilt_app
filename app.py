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
# НАСТРОЙКИ (вынесены в конфиг)
# ------------------------------------------------------------
CONFIG = {
    "BOT_TOKEN": "8538186715:AAG7XsBxp6TAy2lalWQ6_KkBkrUIEZCqxuw",  # заменить
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
# СПЕЦИФИКАЦИИ ДАТЧИКОВ (вынесены в словарь)
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
# КЛАСС ДЛЯ ОБРАБОТКИ ДАННЫХ (бизнес-логика)
# ------------------------------------------------------------
class DataProcessor:
    @staticmethod
    def process_strain_data(df: pd.DataFrame, f0: float, t0: float,
                            sensor_type: str, g_val: Optional[float] = None,
                            c_val: Optional[float] = None) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        """Обработка данных тензодатчика: расчёт деформации и напряжения."""
        if df.empty:
            return None, None

        # Очистка данных
        for col in ['load', 'freq', 'temp']:
            if col not in df.columns:
                return None, None
            df[col] = df[col].astype(str).str.replace(',', '.').str.replace(' ', '')
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna()
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

        # Строим график через matplotlib
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
# ПАРСИНГ СВАЙНЫХ ИСПЫТАНИЙ (вынесен в отдельную функцию)
# ------------------------------------------------------------
def parse_pile_data(file_bytes: bytes) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    debug = []
    xl = pd.ExcelFile(file_bytes)
    sheet_names = xl.sheet_names
    debug.append(f"📋 Найдены листы: {sheet_names}")

    zero_sheet = None
    for name in sheet_names:
        if 'свая' in name.lower() and 'испытания' not in name.lower():
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
                        Psi = CONFIG["PILE_A"] * (f**2) + CONFIG["PILE_B"] * f + CONFIG["PILE_C"] + CONFIG["PILE_K"] * (T - CONFIG["PILE_T_REF"])
                        df_sensor.at[i, 'Давление_расч, Psi'] = Psi
                        df_sensor.at[i, 'Давление_расч, МПа'] = Psi * 0.00689475729317831
                results[sensor_name] = df_sensor
            else:
                results[sensor_name] = df_sensor

    return results, debug

# ------------------------------------------------------------
# ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ
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
# UI-КОМПОНЕНТЫ (вынесены для переиспользования)
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
# ОСНОВНАЯ ФУНКЦИЯ ПРИЛОЖЕНИЯ (Streamlit UI)
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title="Анализ датчиков", layout="wide")
    st.title("📊 Обработка данных тензодатчиков")

    # Инициализация состояния сессии
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
            config = {
                'sensor_type': sensor_type,
                'f0': f0,
                't0': t0,
                'g_val': g_val,
                'c_val': c_val,
                'theme': theme
            }
            # Сохраняем в файл (опционально)
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

1. **Загрузка файла** – выберите Excel-файл с колонками: нагрузка, частота, температура.
2. **Ручной ввод** – вставьте данные из буфера обмена.
3. **Свайные испытания** – загрузите файл с листами "Свая..." и "Испытания".
4. **Подбор датчиков** – выберите параметры и получите рекомендации.
5. **Интерактивная калибровка** – настройте параметры ползунками в реальном времени.
6. **Сравнение датчиков** – загрузите несколько файлов для сравнения.
7. **Настройки** – выберите тип датчика, укажите f₀ и T₀.
8. **Результаты** – скачайте отчёт в Excel, PDF или Word.

**Форматы файлов:** .xlsx, .xls
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
                col_load = st.selectbox("Столбец с нагрузкой (load)", options=[None] + df_raw.columns.tolist(),
                                        index=0 if default_load is None else df_raw.columns.tolist().index(default_load)+1,
                                        key="col_load")
                col_freq = st.selectbox("Столбец с частотой (freq)", options=[None] + df_raw.columns.tolist(),
                                        index=0 if default_freq is None else df_raw.columns.tolist().index(default_freq)+1,
                                        key="col_freq")
                col_temp = st.selectbox("Столбец с температурой (temp)", options=[None] + df_raw.columns.tolist(),
                                        index=0 if default_temp is None else df_raw.columns.tolist().index(default_temp)+1,
                                        key="col_temp")

                if col_load is None or col_freq is None or col_temp is None:
                    st.warning("Пожалуйста, выберите все три столбца.")
                    st.stop()

                df_mapped = df_raw[[col_load, col_freq, col_temp]].copy()
                df_mapped.columns = ['load', 'freq', 'temp']

                # Сохраняем параметры для отчётов
                st.session_state.report_sensor_type = sensor_type
                st.session_state.report_f0 = f0
                st.session_state.report_t0 = t0
                st.session_state.report_g_val = g_val
                st.session_state.report_c_val = c_val

                with st.spinner("Обработка данных..."):
                    result, stats = DataProcessor.process_strain_data(df_mapped, f0, t0, sensor_type, g_val, c_val)

                if result is not None:
                    st.session_state.result = result
                    st.session_state.stats = stats
                    st.session_state.sensor_name = uploaded_file.name
                    display_results(result, stats, uploaded_file.name, sensor_type, f0, t0)
                else:
                    st.error("Ошибка обработки данных. Проверьте формат файла.")

            except Exception as e:
                st.error(f"Ошибка при обработке: {e}")
                logging.error(f"Ошибка: {e}")
                send_telegram(f"Ошибка в загрузке файла: {e}")

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
                            result, stats = DataProcessor.process_strain_data(df_manual, f0, t0, sensor_type, g_val, c_val)

                        if result is not None:
                            st.session_state.result = result
                            st.session_state.stats = stats
                            st.session_state.sensor_name = "Ручной ввод"
                            display_results(result, stats, "Ручной ввод", sensor_type, f0, t0)
                        else:
                            st.error("Ошибка обработки данных. Проверьте формат.")

                except Exception as e:
                    st.error(f"Ошибка при обработке: {e}")
                    logging.error(f"Ошибка ручного ввода: {e}")
                    send_telegram(f"Ошибка ручного ввода: {e}")

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
                                fig = go.Figure()
                                if 'Давление, бар' in df.columns:
                                    press_bar = df.dropna(subset=['Нагрузка, тс', 'Давление, бар'])
                                    if not press_bar.empty:
                                        press_bar['Давление_бар_МПа'] = press_bar['Давление, бар'] * 0.1
                                        fig.add_trace(go.Scatter(x=press_bar['Нагрузка, тс'], y=press_bar['Давление_бар_МПа'],
                                                                 mode='lines+markers', name='Давление (из файла) МПа'))
                                if 'Давление_расч, МПа' in df.columns:
                                    plot_df = df.dropna(subset=['Нагрузка, тс', 'Давление_расч, МПа'])
                                    if not plot_df.empty:
                                        fig.add_trace(go.Scatter(x=plot_df['Нагрузка, тс'], y=plot_df['Давление_расч, МПа'],
                                                                 mode='lines+markers', name='Давление (расч.) МПа'))
                                if fig.data:
                                    fig.update_layout(
                                        title=f"Зависимость давления от нагрузки ({sensor_name})",
                                        xaxis_title="Нагрузка, тс",
                                        yaxis_title="Давление, МПа",
                                        template=st.session_state.template
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
                send_telegram(f"Ошибка обработки свайных данных: {e}")

    # ---------- Вкладка 4: Подбор датчиков ----------
    with tab4:
        st.subheader("📋 Подбор тензодатчиков для задач мониторинга")
        st.markdown("""
        **Калькулятор** помогает выбрать оптимальный тип виброструнного датчика в зависимости от:
        - **измеряемого параметра** (деформация, напряжение, давление грунта и др.),
        - **места установки** (бетон, сталь, грунт),
        - **дополнительных требований** (водонепроницаемость, точность).
        """)

        col1, col2 = st.columns(2)
        with col1:
            parameter = st.selectbox(
                "Что нужно измерять?",
                [
                    "Деформация (осадка, перемещение)",
                    "Напряжение в бетоне/арматуре",
                    "Давление грунта (напряжения в массиве)",
                    "Крен (наклон) конструкции",
                    "Температура (в комплексе с деформацией)"
                ],
                index=0,
                key="param_select"
            )
        with col2:
            surface = st.selectbox(
                "Где устанавливается датчик?",
                [
                    "На поверхность бетона",
                    "Внутрь бетона (встроенный)",
                    "На поверхность стали",
                    "В грунт (засыпка)",
                    "На арматуру (сварка/прикрутка)"
                ],
                index=0,
                key="surface_select"
            )

        col3, col4 = st.columns(2)
        with col3:
            waterproof_required = st.checkbox("Требуется водонепроницаемость (глубокое заложение, > 5 м)", value=False)
        with col4:
            high_accuracy = st.checkbox("Высокая точность (разрешение < 1 μϵ)", value=False)

        if st.button("Подобрать датчик", key="calc_sensor"):
            param_keywords = {
                "Деформация (осадка, перемещение)": "деформация",
                "Напряжение в бетоне/арматуре": "напряжение",
                "Давление грунта (напряжения в массиве)": "давление грунта",
                "Крен (наклон) конструкции": "крен",
                "Температура (в комплексе с деформацией)": "температура"
            }
            param_key = param_keywords.get(parameter, "деформация")

            surface_keywords = {
                "На поверхность бетона": "на поверхность бетона",
                "Внутрь бетона (встроенный)": "внутрь бетона",
                "На поверхность стали": "на поверхность стали",
                "В грунт (засыпка)": "в грунт",
                "На арматуру (сварка/прикрутка)": "на арматуру"
            }
            surface_key = surface_keywords.get(surface, "")

            recommendations = []
            for sensor, features in SENSOR_SPECS.items():
                score = 0
                reasons = []

                # Проверяем параметр
                if param_key in features.get("параметры", []):
                    score += 2
                    reasons.append(f"✓ подходит для измерения '{param_key}'")
                else:
                    reasons.append(f"✗ не предназначен для '{param_key}'")

                # Проверяем поверхность
                if surface_key in features.get("поверхность", []):
                    score += 2
                    reasons.append(f"✓ подходит для монтажа '{surface_key}'")
                else:
                    reasons.append(f"✗ не подходит для '{surface_key}'")

                if waterproof_required:
                    if features.get("водонепроницаемость", False):
                        score += 1
                        reasons.append("✓ обладает водонепроницаемостью")
                    else:
                        reasons.append("✗ недостаточная водозащита")

                if high_accuracy:
                    if features.get("точность") == "высокая":
                        score += 1
                        reasons.append("✓ высокое разрешение")
                    else:
                        reasons.append("✗ среднее разрешение (требуется высокая точность)")

                if score > 0:
                    recommendations.append({
                        "датчик": sensor,
                        "балл": score,
                        "причины": reasons
                    })

            recommendations.sort(key=lambda x: x["балл"], reverse=True)

            if recommendations:
                st.success(f"✅ Найдено {len(recommendations)} подходящих датчиков")
                rows = []
                for rec in recommendations:
                    reasons_text = "; ".join(rec["причины"])
                    rows.append({
                        "Датчик": rec["датчик"],
                        "Совместимость (балл)": rec["балл"],
                        "Обоснование": reasons_text
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

                st.subheader("📘 Детальные характеристики")
                for rec in recommendations:
                    sensor = rec["датчик"]
                    with st.expander(f"📐 {sensor} (совместимость: {rec['балл']} баллов)"):
                        specs_text = get_sensor_specs(sensor)
                        st.text(specs_text)
                        st.markdown("**Рекомендации по монтажу:**")
                        if "MAS‑VWS‑EM15H" in sensor:
                            st.markdown("- Встраивается в бетон при заливке или крепится на арматуру.")
                        elif "MAS‑VWS‑SM15" in sensor:
                            st.markdown("- Приваривается на стальные конструкции или приклеивается на бетон (эпоксидным клеем).")
                        elif "MAS‑VWS‑SM25H" in sensor:
                            st.markdown("- Приваривается на сталь или приклеивается на бетон, подходит для влажной среды (водонепроницаем).")
                        elif "MAS‑VWE" in sensor:
                            st.markdown("- Закапывается в грунт или устанавливается в насыпь, требуется защита кабеля.")
            else:
                st.warning("Не найдено подходящих датчиков. Попробуйте изменить параметры.")

            st.caption("Подбор основан на технических характеристиках датчиков из документации. Окончательное решение принимается проектировщиком.")

    # ---------- Вкладка 5: Интерактивная калибровка ----------
    with tab5:
        st.subheader("🎛️ Интерактивная калибровка датчика")
        st.markdown("""
        Изменяйте параметры ползунками – график и статистика будут пересчитываться **в реальном времени**.
        """)

        if st.session_state.result is not None:
            df_orig = st.session_state.result.copy()

            col1, col2 = st.columns(2)
            with col1:
                f0_cal = st.slider("f₀ (Гц)", min_value=500.0, max_value=2000.0,
                                   value=st.session_state.report_f0, step=0.5, key="f0_cal")
                t0_cal = st.slider("T₀ (°C)", min_value=-20.0, max_value=50.0,
                                   value=st.session_state.report_t0, step=0.5, key="t0_cal")
            with col2:
                g_cal = st.slider("G (если нужен)", min_value=0.5, max_value=2.0,
                                  value=st.session_state.report_g_val or 1.0, step=0.001, key="g_cal")
                c_cal = st.slider("C (если нужен)", min_value=0.5, max_value=2.0,
                                  value=st.session_state.report_c_val or 1.0, step=0.001, key="c_cal")

            sensor_type = st.session_state.report_sensor_type
            if sensor_type in ["MAS‑VWS‑EM15H (встроенный)", "MAS‑VWS‑SM25H (поверхностный длинная база)"]:
                K = CONFIG["DEFAULT_K_EM15H"] if "EM15H" in sensor_type else CONFIG["DEFAULT_K_SM25H"]
            else:
                K = g_cal * c_cal

            df_cal = df_orig.copy()
            df_cal['strain'] = K * (df_cal['freq']**2 - f0_cal**2) + (df_cal['temp'] - t0_cal) * (CONFIG["F_STRING"] - CONFIG["F_CONCRETE"])
            df_cal['stress_MPa'] = CONFIG["E_MODULUS"] * df_cal['strain'] / 1_000_000 * 0.00689476

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_cal['load'], y=df_cal['strain'], mode='lines+markers', name='Деформация, μϵ'))
            fig.update_layout(
                title="Деформация от нагрузки (интерактивная калибровка)",
                xaxis_title="Нагрузка, тс",
                yaxis_title="Деформация, μϵ",
                template=st.session_state.template
            )
            st.plotly_chart(fig, use_container_width=True)

            stats_cal = {
                'Средняя деформация, μϵ': df_cal['strain'].mean(),
                'Макс. деформация, μϵ': df_cal['strain'].max(),
                'Мин. деформация, μϵ': df_cal['strain'].min(),
                'Среднее напряжение, МПа': df_cal['stress_MPa'].mean(),
            }
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Средняя деформация", f"{stats_cal['Средняя деформация, μϵ']:.1f} μϵ")
                st.metric("Макс. деформация", f"{stats_cal['Макс. деформация, μϵ']:.1f} μϵ")
            with col2:
                st.metric("Среднее напряжение", f"{stats_cal['Среднее напряжение, МПа']:.3f} МПа")
                st.metric("Мин. деформация", f"{stats_cal['Мин. деформация, μϵ']:.1f} μϵ")

            if st.button("Применить эти параметры к отчёту"):
                st.session_state.report_f0 = f0_cal
                st.session_state.report_t0 = t0_cal
                st.session_state.report_g_val = g_cal
                st.session_state.report_c_val = c_cal
                st.session_state.result = df_cal
                st.success("Параметры обновлены! Теперь скачивайте отчёт с новыми значениями.")
        else:
            st.info("Сначала загрузите данные в вкладке 'Загрузка файла' или 'Ручной ввод'.")

    # ---------- Вкладка 6: Сравнение датчиков ----------
    with tab6:
        st.subheader("📊 Сравнение нескольких датчиков")
        st.markdown("""
        Загрузите несколько файлов (или вставьте данные) для сравнения на одном графике.
        """)

        uploaded_files = st.file_uploader(
            "Выберите файлы .xlsx или .xls",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="multi_upload"
        )

        compare_what = st.selectbox(
            "Что сравнивать?",
            ["Деформация, μϵ", "Напряжение, МПа", "Частота, Гц"],
            index=0,
            key="compare_what"
        )

        if uploaded_files:
            fig_comp = go.Figure()
            for file in uploaded_files:
                try:
                    df_raw = pd.read_excel(file)
                    if len(df_raw.columns) >= 3:
                        df_comp = df_raw.iloc[:, :3].copy()
                        df_comp.columns = ['load', 'freq', 'temp']
                    else:
                        st.warning(f"Файл {file.name} содержит менее 3 колонок, пропускаем.")
                        continue

                    sensor_type = st.session_state.report_sensor_type
                    if sensor_type in ["MAS‑VWS‑EM15H (встроенный)", "MAS‑VWS‑SM25H (поверхностный длинная база)"]:
                        K = CONFIG["DEFAULT_K_EM15H"] if "EM15H" in sensor_type else CONFIG["DEFAULT_K_SM25H"]
                    else:
                        K = st.session_state.report_g_val * st.session_state.report_c_val if st.session_state.report_g_val and st.session_state.report_c_val else 1.0

                    f0_comp = st.session_state.report_f0
                    t0_comp = st.session_state.report_t0
                    df_comp['strain'] = K * (df_comp['freq']**2 - f0_comp**2) + (df_comp['temp'] - t0_comp) * (CONFIG["F_STRING"] - CONFIG["F_CONCRETE"])
                    df_comp['stress_MPa'] = CONFIG["E_MODULUS"] * df_comp['strain'] / 1_000_000 * 0.00689476

                    y_col = {'Деформация, μϵ': 'strain', 'Напряжение, МПа': 'stress_MPa', 'Частота, Гц': 'freq'}[compare_what]
                    fig_comp.add_trace(go.Scatter(
                        x=df_comp['load'],
                        y=df_comp[y_col],
                        mode='lines+markers',
                        name=file.name
                    ))
                except Exception as e:
                    st.warning(f"Ошибка обработки файла {file.name}: {e}")

            if fig_comp.data:
                fig_comp.update_layout(
                    title=f"Сравнение датчиков по параметру: {compare_what}",
                    xaxis_title="Нагрузка, тс",
                    yaxis_title=compare_what,
                    template=st.session_state.template
                )
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.warning("Не удалось обработать ни одного файла.")
        else:
            st.info("Загрузите файлы для сравнения.")

# ------------------------------------------------------------
# ЗАПУСК
# ------------------------------------------------------------
if __name__ == "__main__":
    main()
