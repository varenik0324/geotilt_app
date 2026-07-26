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
# СПЕЦИФИКАЦИИ ДАТЧИКОВ (ПОЛНЫЙ СЛОВАРЬ)
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
    return "\n".join([f"{k}: {v}" for k, v in specs.items()])

# ------------------------------------------------------------
# ОБРАБОТЧИК ТЕНЗОДАТЧИКОВ (плоские таблицы)
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
        required = ['load', 'freq', 'temp']
        if df.empty:
            return False, "DataFrame пуст.", df
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

    @staticmethod
    def process_strain_data(df: pd.DataFrame, f0: float, t0: float,
                            sensor_type: str, g_val: Optional[float] = None,
                            c_val: Optional[float] = None) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        if df.empty:
            return None, None
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
# ГЕНЕРАЦИЯ ОТЧЁТОВ (PDF, WORD – рабочие функции)
# ------------------------------------------------------------
class ReportGenerator:
    @staticmethod
    def to_excel(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Результат')
            stats_df = pd.DataFrame.from_dict(stats, orient='index', columns=['Значение'])
            stats_df.to_excel(writer, sheet_name='Сводка')
            ws_spec = writer.book.add_worksheet('Спецификация датчика')
            specs_text = get_sensor_specs(sensor_type)
            for i, line in enumerate(specs_text.split('\n')):
                ws_spec.write(i, 0, line)
        return output.getvalue()

    @staticmethod
    def to_pdf(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
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
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, f"Отчёт по датчику: {sensor_name}")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        c.drawString(50, height - 100, f"f₀ = {f0:.1f} Гц, T₀ = {t0:.1f} °C")
        specs_text = get_sensor_specs(sensor_type)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, height - 130, "Спецификация датчика:")
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
        c.drawString(50, height - 480, "Сводка:")
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
    def to_word(df: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str,
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
        doc.add_paragraph(f"f₀ = {f0:.1f} Гц, T₀ = {t0:.1f} °C")
        doc.add_heading("Спецификация датчика", level=2)
        for line in get_sensor_specs(sensor_type).split('\n'):
            doc.add_paragraph(line)
        doc.add_heading("Сводка", level=2)
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
        hdr_cells[2].text = "Температура, °C"
        hdr_cells[3].text = "Деформация, μϵ"
        hdr_cells[4].text = "Напряжение, МПа"
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
        headers = df_test_raw.iloc[start_header].tolist()
        headers = [str(h).strip() if pd.notna(h) else '' for h in headers]

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

        blocks = PileParser._find_header_blocks(df_test_raw)
        if not blocks:
            info['debug'].append("Не найдены блоки с заголовками (нет строк с Время, Нагрузка, Давление).")
            return {}, info

        info['debug'].append(f"Найдено блоков: {len(blocks)}")

        zero_data = {}
        for sheet in zero_sheets:
            df_zero_raw = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            df_zero_raw.columns = range(df_zero_raw.shape[1])
            zero_data.update(PileParser._extract_zero_data(df_zero_raw))

        info['debug'].append(f"Нулевых значений получено: {len(zero_data)}")

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
        uploaded_file = st.file_uploader("Выберите Excel-файл", type=["xlsx", "xls"], key="file_uploader_flat")
        if uploaded_file:
            try:
                df_raw = pd.read_excel(uploaded_file)
                if len(df_raw.columns) >= 3:
                    df_mapped = df_raw.iloc[:, :3].copy()
                    df_mapped.columns = ['load', 'freq', 'temp']
                    valid, msg, df_clean = DataProcessor.validate_data(df_mapped)
                    if valid:
                        st.success(msg)
                        result, stats = DataProcessor.process_strain_data(df_clean, f0, t0, sensor_type, g_val, c_val)
                        if result is not None:
                            st.session_state.result = result
                            st.session_state.stats = stats
                            st.session_state.sensor_name = uploaded_file.name
                            st.dataframe(result)
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(x=result['load'], y=result['strain'], mode='lines+markers', name='Деформация, μϵ'))
                            fig.update_layout(template=st.session_state.template)
                            st.plotly_chart(fig, use_container_width=True)

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                excel_data = ReportGenerator.to_excel(result, stats, uploaded_file.name, sensor_type)
                                st.download_button(
                                    label="📊 Excel",
                                    data=excel_data,
                                    file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                            with col2:
                                pdf_data = ReportGenerator.to_pdf(result, stats, uploaded_file.name, sensor_type, f0, t0)
                                st.download_button(
                                    label="📄 PDF",
                                    data=pdf_data.getvalue(),
                                    file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                    mime="application/pdf"
                                )
                            with col3:
                                word_data = ReportGenerator.to_word(result, stats, uploaded_file.name, sensor_type, f0, t0)
                                st.download_button(
                                    label="📝 Word",
                                    data=word_data.getvalue(),
                                    file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                )
                        else:
                            st.error("Ошибка расчёта.")
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
        st.markdown("Вставьте данные в формате: нагрузка, частота, температура (разделитель – пробел, запятая или табуляция).")
        text_data = st.text_area("Введите данные", height=200)
        if st.button("Обработать"):
            if not text_data.strip():
                st.warning("Введите данные.")
            else:
                try:
                    lines = text_data.strip().splitlines()
                    rows = []
                    for line in lines:
                        if line.strip():
                            parts = re.split(r'[,\t; ]+', line.strip())
                            if len(parts) >= 3:
                                rows.append(parts[:3])
                    if not rows:
                        st.error("Не удалось распознать данные.")
                    else:
                        df_manual = pd.DataFrame(rows, columns=['load', 'freq', 'temp'])
                        valid, msg, df_clean = DataProcessor.validate_data(df_manual)
                        if valid:
                            st.success(msg)
                            result, stats = DataProcessor.process_strain_data(df_clean, f0, t0, sensor_type, g_val, c_val)
                            if result is not None:
                                st.session_state.result = result
                                st.session_state.stats = stats
                                st.session_state.sensor_name = "Ручной ввод"
                                st.dataframe(result)
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(x=result['load'], y=result['strain'], mode='lines+markers', name='Деформация, μϵ'))
                                fig.update_layout(template=st.session_state.template)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.error("Ошибка расчёта.")
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"Ошибка: {e}")

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
            # Превью первых 30 строк для ручной настройки
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

    # ---------- Вкладки 4-6 (заглушки для будущего расширения) ----------
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
