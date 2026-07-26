import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import io
import re
import logging
import sqlite3
import requests
import os
import sys
import json
import tempfile
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
CONFIG = {
    "BOT_TOKEN": "8538186715:AAG7XsBxp6TAy2lalWQ6_KkBkrUIEZCqxuw",
    "CHAT_ID": "1278271780",
    "LOG_FILE": "app_errors.log",
    "DB_FILE": "measurements.db",
    "PROFILES_FILE": "profiles.json",
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

# ============================================================
# 2. УТИЛИТЫ
# ============================================================
def clean_numeric(val):
    if pd.isna(val):
        return np.nan
    if isinstance(val, str):
        val = val.replace(',', '.').replace(' ', '').strip()
        return float(val) if val and val != '-' else np.nan
    return val

def send_telegram(message: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{CONFIG['BOT_TOKEN']}/sendMessage"
        payload = {"chat_id": CONFIG['CHAT_ID'], "text": f"📩 {message}", "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except Exception as e:
        logging.error(f"Telegram exception: {e}")
        return False

def save_profile(profile: Dict):
    profiles = {}
    if os.path.exists(CONFIG["PROFILES_FILE"]):
        with open(CONFIG["PROFILES_FILE"], 'r', encoding='utf-8') as f:
            profiles = json.load(f)
    profiles[profile['name']] = profile
    with open(CONFIG["PROFILES_FILE"], 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)

def load_profiles() -> Dict:
    if os.path.exists(CONFIG["PROFILES_FILE"]):
        with open(CONFIG["PROFILES_FILE"], 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_pdf_path(filename: str) -> Optional[str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(base_dir, 'docs', filename)
    if os.path.exists(pdf_path):
        return pdf_path
    return None

# ============================================================
# 3. СПЕЦИФИКАЦИИ ДАТЧИКОВ (расширенные из PDF-руководств)
# ============================================================
SENSOR_SPECS = {
    "MAS‑VWS‑EM15H (встроенный)": {
        "type": "Виброструнный тензометр (встроенный)",
        "k_factor": "0.0031559",
        "measuring_range": "±1500 μϵ",
        "accuracy": "0.5% F.S",
        "resolution": "1.0 μϵ",
        "temperature_range": "-20…+80 °C",
        "temperature_accuracy": "±0.5 °C",
        "waterproof": "≥0.5 МПа",
        "gauge_length": "150 мм",
        "thermal_expansion_steel": "12.2 μϵ/°C",
        "thermal_expansion_concrete": "10.0 μϵ/°C",
        "application": "Мониторинг мостов, зданий, плотин, труб, свай.",
        "installation": "Встраивается в бетон при заливке или крепится на арматуру.",
        "principle": "Принцип работы основан на виброструнном методе: изменение деформации конструкции передаётся на стальную струну, меняя её частоту колебаний.",
        "pdf_file": "MAS-VWS-EM15H.pdf"
    },
    "MAS‑VWS‑SM15 (поверхностный)": {
        "type": "Виброструнный тензометр (поверхностный, короткая база)",
        "k_factor": "G × C (из сертификата)",
        "measuring_range": "±1500 μϵ",
        "accuracy": "0.5% F.S",
        "sensitivity": "≤0.125% FS",
        "resolution": "1.0 μϵ",
        "temperature_range": "-20…+80 °C",
        "temperature_accuracy": "±0.5 °C",
        "waterproof": "≥0.5 МПа",
        "gauge_length": "150 мм",
        "thermal_expansion_steel": "12.2 μϵ/°C",
        "thermal_expansion_concrete": "10.0 μϵ/°C (зависит от бетона)",
        "application": "Мониторинг строительных конструкций, мостов, тоннелей, свай.",
        "installation": "Приваривается на стальные конструкции или приклеивается на бетон (эпоксидным клеем). Для бетона используются анкерные головки или специальный клей.",
        "principle": "Виброструнный датчик: деформация основания передаётся на струну, частота колебаний которой пропорциональна деформации.",
        "pdf_file": "MAS-VWS-SM15.pdf"
    },
    "MAS‑VWS‑SM25H (поверхностный длинная база)": {
        "type": "Виброструнный тензометр (поверхностный, длинная база)",
        "k_factor": "0.0035708",
        "measuring_range": "±2500 μϵ",
        "accuracy": "0.5% F.S",
        "resolution": "0.1 μϵ",
        "temperature_range": "-40…+90 °C",
        "temperature_accuracy": "±0.5 °C",
        "waterproof": "≥0.5 МПа (глубина до 150 м)",
        "gauge_length": "129 мм",
        "thermal_expansion_steel": "12.2 μϵ/°C",
        "thermal_expansion_concrete": "10.0 μϵ/°C",
        "application": "Мониторинг больших конструкций (плотины, мосты, тоннели), где требуется высокая точность и большой диапазон.",
        "installation": "Приваривается на сталь или приклеивается на бетон. Для бетона используются анкерные болты или специальный клей. Требует тщательной подготовки поверхности.",
        "principle": "Классический виброструнный принцип: натянутая струна изменяет частоту при деформации, что позволяет с высокой точностью измерять относительные деформации.",
        "pdf_file": "MAS-VWS-SM25H.pdf"
    },
    "MAS‑VWE (давление грунта)": {
        "type": "Виброструнный датчик давления грунта",
        "k_factor": "G × C (из сертификата)",
        "measuring_range": "0…350/700/1000/2000/3000 кПа",
        "accuracy": "0.5% F.S",
        "resolution": "0.01 кПа",
        "temperature_range": "-40…+80 °C",
        "temperature_accuracy": "±0.5 °C (@ -10…70 °C)",
        "waterproof": "≥1.0 МПа (до 1.2 × номинального давления)",
        "over_range": "1.5 × номинального давления",
        "insulation_resistance": "≥50 МОм",
        "size": "Φ25×160 мм",
        "application": "Мониторинг земляных плотин, откосов, дорожных насыпей, подпорных стен, тоннелей. Измерение напряжений в грунте.",
        "installation": "Закапывается в грунт или устанавливается в насыпь, требуется защита кабеля. Для надёжного контакта с грунтом необходима обратная засыпка с трамбовкой.",
        "principle": "Давление грунта деформирует чувствительный элемент, который передаёт деформацию на виброструнный преобразователь, изменяя его частоту.",
        "pdf_file": "MAS-VWE.pdf"
    }
}

def get_sensor_specs(sensor_type: str) -> str:
    specs = SENSOR_SPECS.get(sensor_type, {})
    if not specs:
        return "Характеристики не найдены."
    lines = [
        f"🔹 Тип: {specs.get('type', 'не указан')}",
        f"📏 Длина базы: {specs.get('gauge_length', 'не указана')}",
        f"📊 Диапазон измерений: {specs.get('measuring_range', 'не указан')}",
        f"🎯 Точность: {specs.get('accuracy', 'не указана')}",
        f"🔬 Разрешение: {specs.get('resolution', 'не указано')}",
        f"🌡️ Диапазон температур: {specs.get('temperature_range', 'не указан')}",
        f"🌡️ Точность температуры: {specs.get('temperature_accuracy', 'не указана')}",
        f"💧 Водонепроницаемость: {specs.get('waterproof', 'не указана')}",
        f"🔧 Коэффициент K: {specs.get('k_factor', 'не указан')}",
        f"🧊 Коэф. теплового расширения (сталь): {specs.get('thermal_expansion_steel', 'не указан')}",
        f"🧊 Коэф. теплового расширения (бетон): {specs.get('thermal_expansion_concrete', 'не указан')}",
        f"📌 Применение: {specs.get('application', 'не указано')}",
        f"🔩 Монтаж: {specs.get('installation', 'не указан')}",
        f"⚙️ Принцип работы: {specs.get('principle', 'не указан')}"
    ]
    return "\n".join(lines)

# ============================================================
# 4. ОБРАБОТЧИК ТЕНЗОДАТЧИКОВ
# ============================================================
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
        if df is None or df.empty:
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
        if df is None or df.empty:
            return None, None
        K = {
            'MAS‑VWS‑EM15H (встроенный)': CONFIG["DEFAULT_K_EM15H"],
            'MAS‑VWS‑SM25H (поверхностный длинная база)': CONFIG["DEFAULT_K_SM25H"]
        }.get(sensor_type)
        if K is None and sensor_type in ['MAS‑VWS‑SM15 (поверхностный)', 'MAS‑VWE (давление грунта)']:
            if g_val is None or c_val is None:
                return None, None
            K = g_val * c_val
        if K is None:
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
            'Std деформация, μϵ': df['strain'].std(),
            'Статистика': df['strain'].describe().to_dict()
        }
        return df, stats

# ============================================================
# 5. ГЕНЕРАЦИЯ ОТЧЁТОВ
# ============================================================
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
        from reportlab.lib.utils import ImageReader
        import matplotlib.pyplot as plt
        from PIL import Image

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
            if key not in ['Статистика']:
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
            if key not in ['Статистика']:
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

# ============================================================
# 6. ПАРСЕР СВАЙНЫХ ИСПЫТАНИЙ
# ============================================================
class PileParser:
    @staticmethod
    def find_sheets(file_bytes: bytes) -> Tuple[Optional[str], List[str]]:
        xl = pd.ExcelFile(file_bytes)
        sheets = xl.sheet_names
        test_sheet = next((s for s in sheets if 'испытания' in s.lower() or 'испыт' in s.lower()), None)
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
        zero_sheets = [s for s in sheets if s != test_sheet and ('свая' in s.lower() or 'нулевой' in s.lower())]
        if not zero_sheets:
            for name in sheets:
                if name == test_sheet:
                    continue
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
        header_row = None
        freq_col = temp_col = None
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
            if sensor_pattern.search(first_cell) or any(k in first_cell.lower() for k in ['верх', 'сред', 'низ']):
                sensor_name = first_cell
                f_val = row[freq_col] if freq_col < len(row) and pd.notna(row[freq_col]) else np.nan
                t_val = row[temp_col] if temp_col < len(row) and pd.notna(row[temp_col]) else np.nan
                if not pd.isna(f_val) and not pd.isna(t_val):
                    zero_data[sensor_name] = {'f0': f_val, 'T0': t_val}
        return zero_data

    @staticmethod
    def _find_header_blocks(df_test_raw: pd.DataFrame) -> List[Dict]:
        header_rows = []
        keywords = ['время', 'нагрузк', 'давлен']
        for idx, row in df_test_raw.iterrows():
            row_text = ' '.join([str(c) for c in row if pd.notna(c)])
            row_lower = row_text.lower()
            if all(kw in row_lower for kw in keywords):
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
            blocks.append({'name': pile_name, 'start_header': h_row, 'end': end_row})
        return blocks

    @staticmethod
    def _extract_block_data(df_test_raw: pd.DataFrame, start_header: int, end_row: int,
                            zero_data: Dict, sensor_col: int = 0) -> Dict[str, pd.DataFrame]:
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
            first_cell = str(row[sensor_col]).strip() if len(row) > sensor_col else ''
            if not first_cell:
                continue
            if any(phrase in first_cell for phrase in exclude_phrases):
                continue
            if sensor_pattern.search(first_cell) or any(k in first_cell.lower() for k in ['верх', 'сред', 'низ']):
                sensor_rows.append(idx)

        block_results = {}
        for idx in sensor_rows:
            row = df_test_raw.iloc[idx]
            sensor_name = str(row[sensor_col]).strip() if len(row) > sensor_col else f"Датчик_{idx}"
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
                        A, B, C, K, T_ref = CONFIG["PILE_A"], CONFIG["PILE_B"], CONFIG["PILE_C"], CONFIG["PILE_K"], CONFIG["PILE_T_REF"]
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
    def parse_pile_data(file_bytes: bytes, manual_header: Optional[int] = None,
                        manual_sensor_col: int = 0) -> Tuple[Dict[str, pd.DataFrame], Dict]:
        test_sheet, zero_sheets = PileParser.find_sheets(file_bytes)
        info = {'test_sheet': test_sheet, 'zero_sheets': zero_sheets, 'debug': []}
        if not test_sheet:
            info['debug'].append("Лист испытаний не найден.")
            return {}, info
        if not zero_sheets:
            info['debug'].append("Нулевые листы не найдены.")
            return {}, info
        info['debug'].append(f"Лист испытаний: {test_sheet}")
        info['debug'].append(f"Нулевые листы: {zero_sheets}")

        df_test_raw = pd.read_excel(file_bytes, sheet_name=test_sheet, header=None)
        df_test_raw.columns = range(df_test_raw.shape[1])

        if manual_header is not None:
            blocks = [{'name': 'Ручной блок', 'start_header': manual_header, 'end': len(df_test_raw)}]
        else:
            blocks = PileParser._find_header_blocks(df_test_raw)
        info['debug'].append(f"Найдено блоков: {len(blocks)}")

        zero_data = {}
        if zero_sheets:
            df_zero_raw = pd.read_excel(file_bytes, sheet_name=zero_sheets[0], header=None)
            df_zero_raw.columns = range(df_zero_raw.shape[1])
            zero_data = PileParser._extract_zero_data(df_zero_raw)
        info['debug'].append(f"Нулевых значений: {len(zero_data)}")

        all_results = {}
        for block in blocks:
            block_results = PileParser._extract_block_data(
                df_test_raw,
                block['start_header'],
                block['end'],
                zero_data,
                manual_sensor_col
            )
            all_results.update(block_results)

        info['debug'].append(f"Обработано датчиков: {len(all_results)}")
        return all_results, info

# ============================================================
# 7. UI-ФУНКЦИИ
# ============================================================
def show_pile_results(results: Dict[str, pd.DataFrame], info: Dict):
    if not results:
        st.error("Данные не найдены. Проверьте структуру файла.")
        with st.expander("🔍 Отладка", expanded=True):
            for msg in info.get('debug', []):
                st.code(msg)
        return
    st.success(f"✅ Обработано датчиков: {len(results)}")
    with st.expander("🔍 Отладка"):
        for msg in info.get('debug', []):
            st.code(msg)
    sensor_names = list(results.keys())
    selected = st.multiselect("Выберите датчики", sensor_names, default=sensor_names[:3])
    for sensor in selected:
        df = results[sensor]
        with st.expander(f"📊 {sensor} (строк: {len(df)})", expanded=True):
            st.dataframe(df)
            if 'Нагрузка, тс' in df and 'Давление, бар' in df:
                plot_df = df.dropna(subset=['Нагрузка, тс', 'Давление, бар'])
                if not plot_df.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=plot_df['Нагрузка, тс'], y=plot_df['Давление, бар'],
                                             mode='lines+markers', name='Давление (файл)'))
                    if 'Давление_расч, МПа' in plot_df:
                        fig.add_trace(go.Scatter(x=plot_df['Нагрузка, тс'], y=plot_df['Давление_расч, МПа']*10,
                                                 mode='lines+markers', name='Давление (расч.)'))
                    fig.update_layout(
                        title=f"Зависимость давления от нагрузки ({sensor})",
                        xaxis_title="Нагрузка, тс",
                        yaxis_title="Давление, бар",
                        template=st.session_state.get('template', 'plotly_white')
                    )
                    st.plotly_chart(fig, use_container_width=True)
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(f"📥 CSV для {sensor}", data=csv, file_name=f"{sensor}.csv", mime="text/csv")

def display_flat_results(result: pd.DataFrame, stats: Dict, sensor_name: str, sensor_type: str):
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
    
    with st.expander("📊 Расширенная статистика"):
        stats_df = pd.DataFrame.from_dict(stats, orient='index', columns=['Значение'])
        st.dataframe(stats_df)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        excel_data = ReportGenerator.to_excel(result, stats, sensor_name, sensor_type)
        st.download_button(
            label="📊 Excel",
            data=excel_data,
            file_name=f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        pdf_data = ReportGenerator.to_pdf(result, stats, sensor_name, sensor_type, 
                                         st.session_state.get('f0', 1000.0), 
                                         st.session_state.get('t0', 20.0))
        st.download_button(
            label="📄 PDF",
            data=pdf_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf"
        )
    with col3:
        word_data = ReportGenerator.to_word(result, stats, sensor_name, sensor_type,
                                           st.session_state.get('f0', 1000.0),
                                           st.session_state.get('t0', 20.0))
        st.download_button(
            label="📝 Word",
            data=word_data.getvalue(),
            file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

# ============================================================
# 8. ОСНОВНОЕ ПРИЛОЖЕНИЕ (С ОБНОВЛЁННЫМИ ССЫЛКАМИ)
# ============================================================
def main():
    st.set_page_config(
        page_title="Анализ датчиков | Геофундамент",
        page_icon="📐",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Инициализация состояния
    for key in ['result', 'stats', 'sensor_name', 'template', 'f0', 't0', 'profiles', 'page']:
        if key not in st.session_state:
            if key == 'template':
                st.session_state[key] = 'plotly_white'
            elif key in ['f0', 't0']:
                st.session_state[key] = 1000.0 if key == 'f0' else 20.0
            elif key == 'page':
                st.session_state[key] = 'Главная'
            else:
                st.session_state[key] = None if key not in ['profiles'] else {}

    # Шапка
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        st.image("https://via.placeholder.com/80x40?text=GF", width=80)
    with col2:
        st.title("📊 Анализ данных тензодатчиков")
    with col3:
        theme_toggle = st.toggle("🌙 Тёмная тема", value=st.session_state.template == 'plotly_dark')
        st.session_state.template = 'plotly_dark' if theme_toggle else 'plotly_white'

    # Боковая панель
    with st.sidebar:
        st.markdown("### 🧭 Навигация")
        pages = {
            "🏠 Главная": "Главная",
            "📂 Загрузка": "Загрузка",
            "✏️ Ручной ввод": "Ручной ввод",
            "🧪 Свайные испытания": "Свайные испытания",
            "📋 Подбор датчиков": "Подбор датчиков",
            "📈 Калибровка": "Калибровка",
            "📊 Сравнение": "Сравнение",
            "📚 Справка": "Справка"
        }
        selected_page = st.radio("", list(pages.keys()), index=list(pages.values()).index(st.session_state.page))
        st.session_state.page = pages[selected_page]
        
        st.markdown("---")
        st.markdown("### ⚙️ Параметры датчика")
        sensor_type = st.selectbox("Тип датчика", list(SENSOR_SPECS.keys()), key="sensor_type")
        specs = SENSOR_SPECS.get(sensor_type)
        if specs:
            st.caption(f"**K:** {specs.get('k_factor')}")
            st.caption(f"**Диапазон:** {specs.get('measuring_range')}")
            
            with st.expander("📄 Полная спецификация датчика", expanded=False):
                st.text(get_sensor_specs(sensor_type))
            
            pdf_file = specs.get('pdf_file')
            if pdf_file:
                pdf_path = get_pdf_path(pdf_file)
                if pdf_path:
                    with open(pdf_path, 'rb') as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="📄 Скачать PDF-руководство",
                        data=pdf_bytes,
                        file_name=pdf_file,
                        mime="application/pdf"
                    )
                else:
                    st.markdown(f"[📄 Скачать руководство с сайта производителя](https://www.masios.com/docs/{pdf_file})")
            else:
                st.caption("PDF-руководство не доступно")
        
        g_val = c_val = None
        if sensor_type in ["MAS‑VWS‑SM15 (поверхностный)", "MAS‑VWE (давление грунта)"]:
            g_val = st.number_input("G", value=1.0, step=0.001, format="%.3f", key="g_val")
            c_val = st.number_input("C", value=1.0, step=0.001, format="%.3f", key="c_val")
        
        f0 = st.number_input("f₀ (Гц)", value=st.session_state.f0, step=0.1, key="f0_input")
        t0 = st.number_input("T₀ (°C)", value=st.session_state.t0, step=0.1, key="t0_input")
        st.session_state.f0 = f0
        st.session_state.t0 = t0
        
        st.markdown("---")
        profile_name = st.text_input("💾 Сохранить профиль", value="default")
        if st.button("💾 Сохранить"):
            profile = {
                'name': profile_name,
                'sensor_type': sensor_type,
                'f0': f0,
                't0': t0,
                'g_val': g_val,
                'c_val': c_val,
                'theme': 'Тёмная' if theme_toggle else 'Светлая'
            }
            save_profile(profile)
            st.success("Профиль сохранён!")
        
        profiles = load_profiles()
        if profiles:
            profile_names = list(profiles.keys())
            selected_profile = st.selectbox("📂 Загрузить профиль", [""] + profile_names)
            if selected_profile and st.button("📂 Загрузить"):
                p = profiles[selected_profile]
                st.session_state.sensor_type = p.get('sensor_type', 'MAS‑VWS‑EM15H (встроенный)')
                st.session_state.f0 = p.get('f0', 1000.0)
                st.session_state.t0 = p.get('t0', 20.0)
                if 'g_val' in p:
                    st.session_state.g_val = p['g_val']
                if 'c_val' in p:
                    st.session_state.c_val = p['c_val']
                st.rerun()

    # ---- Основные вкладки ----
    page = st.session_state.page
    
    if page == "Главная":
        st.markdown("## 🏠 Дашборд")
        st.markdown("Добро пожаловать в приложение для анализа данных тензодатчиков!")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 Загружено файлов", "0", delta=None)
        with col2:
            st.metric("📈 Обработано датчиков", "0", delta=None)
        with col3:
            st.metric("📅 Последний запуск", datetime.now().strftime("%d.%m.%Y"))
        
        if st.session_state.result is not None:
            st.markdown("### 📊 Последние результаты")
            st.dataframe(st.session_state.result.head(10))
        else:
            st.info("Нет загруженных данных. Перейдите в раздел 'Загрузка' или 'Ручной ввод'.")
        
        # Полезные ссылки (ОБНОВЛЕНО)
        st.markdown("### 🔗 Полезные ресурсы")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            - [📖 Документация по тензодатчикам](https://example.com/docs)
            - [🎥 Видео-туториал](https://example.com/video)
            - [📄 Статья о датчиках давления грунта и деформаций](https://geofundament.ru/datchiki-davlenija-grunta-mesdoza-i-datchiki-deformacij-tenzodatchiki/)
            """)
        with col2:
            st.markdown("""
            - [📄 Статья о мониторинге](https://example.com/article)
            - [💬 Чат поддержки](https://example.com/chat)
            """)
    
    elif page == "Загрузка":
        st.markdown("## 📂 Загрузка файла (плоская таблица)")
        st.markdown("Файл должен содержать колонки: **нагрузка (load)**, **частота (freq)**, **температура (temp)**.")
        uploaded = st.file_uploader("Выберите Excel-файл", type=["xlsx", "xls"], key="flat_upload")
        if uploaded:
            try:
                df_raw = pd.read_excel(uploaded)
                st.write("📋 Предпросмотр загруженных данных:")
                st.dataframe(df_raw.head(10))
                
                if len(df_raw.columns) >= 3:
                    cols = df_raw.columns.tolist()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        load_col = st.selectbox("Столбец с нагрузкой", cols, index=0)
                    with col2:
                        freq_col = st.selectbox("Столбец с частотой", cols, index=1 if len(cols)>1 else 0)
                    with col3:
                        temp_col = st.selectbox("Столбец с температурой", cols, index=2 if len(cols)>2 else 0)
                    
                    if load_col and freq_col and temp_col:
                        df_mapped = df_raw[[load_col, freq_col, temp_col]].copy()
                        df_mapped.columns = ['load', 'freq', 'temp']
                        
                        st.subheader("✏️ Редактирование данных (опционально)")
                        edited_df = st.data_editor(df_mapped, num_rows="dynamic", use_container_width=True)
                        
                        if st.button("🚀 Обработать данные", key="process_flat"):
                            ok, msg, df_clean = DataProcessor.validate_data(edited_df)
                            if ok:
                                st.success(msg)
                                result, stats = DataProcessor.process_strain_data(
                                    df_clean, f0, t0, sensor_type, g_val, c_val
                                )
                                if result is not None and not result.empty:
                                    st.session_state.result = result
                                    st.session_state.stats = stats
                                    st.session_state.sensor_name = uploaded.name
                                    display_flat_results(result, stats, uploaded.name, sensor_type)
                                else:
                                    st.error("Ошибка расчёта. Проверьте данные и настройки датчика.")
                            else:
                                st.error(msg)
                else:
                    st.warning("Файл должен содержать минимум 3 колонки.")
            except Exception as e:
                st.error(f"Ошибка: {e}")
                logging.error(f"Ошибка в загрузке: {e}")
    
    elif page == "Ручной ввод":
        st.markdown("## ✏️ Ручной ввод данных")
        st.markdown("Вставьте данные в формате: **нагрузка, частота, температура**.")
        st.markdown("Поддерживаются разделители: **запятая**, **табуляция**, **пробел**, **точка с запятой**.")
        
        delimiter = st.selectbox("Выберите разделитель", 
                                 ["Авто", "Запятая (,)", "Табуляция (\\t)", "Пробел", "Точка с запятой (;)"],
                                 index=0)
        sep_map = {
            "Авто": None,
            "Запятая (,)": ",",
            "Табуляция (\\t)": "\t",
            "Пробел": " ",
            "Точка с запятой (;)": ";"
        }
        sep = sep_map[delimiter]
        
        text = st.text_area("Введите данные (каждая строка – одна точка)", height=200)
        
        if st.button("🔄 Предпросмотр", key="preview_manual"):
            if not text.strip():
                st.warning("Введите данные.")
            else:
                try:
                    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
                    rows = []
                    for line in lines:
                        if sep:
                            parts = line.split(sep)
                        else:
                            parts = re.split(r'[,\t; ]+', line)
                        parts = [p.strip() for p in parts if p.strip()]
                        if len(parts) >= 3:
                            rows.append(parts[:3])
                    if not rows:
                        st.error("Не удалось распознать данные. Проверьте разделитель.")
                    else:
                        df_preview = pd.DataFrame(rows, columns=['load', 'freq', 'temp'])
                        st.write("📋 Распознанные данные:")
                        st.dataframe(df_preview)
                        st.session_state['manual_df'] = df_preview
                except Exception as e:
                    st.error(f"Ошибка предпросмотра: {e}")
        
        if 'manual_df' in st.session_state and st.session_state['manual_df'] is not None:
            st.subheader("✏️ Редактирование данных")
            edited_df = st.data_editor(st.session_state['manual_df'], num_rows="dynamic", use_container_width=True)
            
            if st.button("🚀 Обработать данные", key="process_manual"):
                ok, msg, df_clean = DataProcessor.validate_data(edited_df)
                if ok:
                    st.success(msg)
                    result, stats = DataProcessor.process_strain_data(
                        df_clean, f0, t0, sensor_type, g_val, c_val
                    )
                    if result is not None and not result.empty:
                        st.session_state.result = result
                        st.session_state.stats = stats
                        st.session_state.sensor_name = "Ручной ввод"
                        display_flat_results(result, stats, "Ручной ввод", sensor_type)
                    else:
                        st.error("Ошибка расчёта.")
                else:
                    st.error(msg)
    
    elif page == "Свайные испытания":
        st.markdown("## 🧪 Свайные испытания")
        st.markdown("""
        Загрузите файл с листами **'Свая ...'** и **'ИСПЫТАНИЯ'**.  
        **Автоматический парсер** найдет данные. Если не сработает – используйте **ручную настройку**.
        """)
        uploaded_pile = st.file_uploader("Выберите .xlsx", type=["xlsx"], key="pile_upload")
        if uploaded_pile:
            file_bytes = uploaded_pile.read()
            df_preview = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=None, nrows=30)
            st.subheader("📋 Превью файла (первые 30 строк)")
            st.dataframe(df_preview)

            with st.expander("⚙️ Ручная настройка (если автоматика не сработала)", expanded=False):
                manual_header = st.number_input("Строка заголовков (0-индекс)", min_value=0, max_value=50, value=4, step=1)
                sensor_col = st.number_input("Столбец с датчиками (0-индекс)", min_value=0, max_value=20, value=0, step=1)
                use_manual = st.checkbox("Использовать ручные настройки")

            try:
                with st.spinner("Обработка файла..."):
                    results, info = PileParser.parse_pile_data(
                        file_bytes,
                        manual_header=manual_header if use_manual else None,
                        manual_sensor_col=sensor_col
                    )
                show_pile_results(results, info)
            except Exception as e:
                st.error(f"Ошибка при обработке: {e}")
                logging.error(f"Ошибка парсинга: {e}")
                send_telegram(f"Ошибка парсинга: {e}")
    
    elif page == "Подбор датчиков":
        st.markdown("## 📋 Подбор датчиков")
        st.markdown("Выберите параметры, и система предложит подходящие датчики.")
        
        col1, col2 = st.columns(2)
        with col1:
            meas_param = st.selectbox("Измеряемый параметр", 
                                     ["Деформация", "Давление", "Напряжение", "Температура"])
            range_req = st.selectbox("Требуемый диапазон", ["±1500 μϵ", "±2500 μϵ", "0-350 кПа", "0-700 кПа", "0-1000 кПа"])
        with col2:
            accuracy_req = st.selectbox("Требуемая точность", ["0.5% F.S", "0.1% F.S"])
            temp_range = st.selectbox("Диапазон температур", ["-20…+80 °C", "-40…+90 °C", "-20…+60 °C"])
        
        if st.button("🔍 Подобрать датчик"):
            recommendations = []
            for sensor, specs in SENSOR_SPECS.items():
                score = 0
                reasons = []
                if meas_param.lower() in specs.get('application', '').lower():
                    score += 2
                    reasons.append(f"✓ подходит для {meas_param}")
                if range_req in specs.get('measuring_range', ''):
                    score += 2
                    reasons.append(f"✓ диапазон {range_req}")
                if accuracy_req in specs.get('accuracy', ''):
                    score += 1
                    reasons.append(f"✓ точность {accuracy_req}")
                if temp_range in specs.get('temperature_range', ''):
                    score += 1
                    reasons.append(f"✓ температурный диапазон {temp_range}")
                if score > 0:
                    recommendations.append({"Датчик": sensor, "Совместимость": score, "Обоснование": "; ".join(reasons)})
            
            if recommendations:
                df_rec = pd.DataFrame(recommendations).sort_values('Совместимость', ascending=False)
                st.dataframe(df_rec, use_container_width=True)
                st.info("Рекомендация: выберите датчик с максимальной совместимостью.")
            else:
                st.warning("Не найдено подходящих датчиков. Попробуйте изменить параметры.")
    
    elif page == "Калибровка":
        st.markdown("## 🎛️ Интерактивная калибровка")
        st.markdown("Изменяйте параметры ползунками и наблюдайте за изменением графика и статистики.")
        
        if st.session_state.result is not None:
            df_orig = st.session_state.result.copy()
            
            col1, col2 = st.columns(2)
            with col1:
                f0_cal = st.slider("f₀ (Гц)", min_value=500.0, max_value=2000.0, value=f0, step=0.5)
                t0_cal = st.slider("T₀ (°C)", min_value=-20.0, max_value=50.0, value=t0, step=0.5)
            with col2:
                g_cal = st.slider("G (если нужен)", min_value=0.5, max_value=2.0, value=g_val or 1.0, step=0.001)
                c_cal = st.slider("C (если нужен)", min_value=0.5, max_value=2.0, value=c_val or 1.0, step=0.001)
            
            result_cal, stats_cal = DataProcessor.process_strain_data(
                df_orig, f0_cal, t0_cal, sensor_type, g_cal, c_cal
            )
            
            if result_cal is not None:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=result_cal['load'], y=result_cal['strain'], 
                                        mode='lines+markers', name='Деформация, μϵ'))
                fig.update_layout(
                    title="Деформация от нагрузки (калибровка)",
                    xaxis_title="Нагрузка, тс",
                    yaxis_title="Деформация, μϵ",
                    template=st.session_state.template
                )
                st.plotly_chart(fig, use_container_width=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Средняя деформация", f"{stats_cal['Средняя деформация, μϵ']:.1f} μϵ")
                    st.metric("Макс. деформация", f"{stats_cal['Макс. деформация, μϵ']:.1f} μϵ")
                with col2:
                    st.metric("Среднее напряжение", f"{stats_cal['Среднее напряжение, МПа']:.3f} МПа")
                    st.metric("Мин. деформация", f"{stats_cal['Мин. деформация, μϵ']:.1f} μϵ")
                
                if st.button("✅ Применить эти параметры к основному результату"):
                    st.session_state.f0 = f0_cal
                    st.session_state.t0 = t0_cal
                    st.session_state.result = result_cal
                    st.session_state.stats = stats_cal
                    st.success("Параметры обновлены!")
        else:
            st.info("Сначала загрузите или введите данные в одной из предыдущих вкладок.")
    
    elif page == "Сравнение":
        st.markdown("## 📊 Сравнение нескольких датчиков")
        st.markdown("Загрузите несколько файлов для сравнения на одном графике.")
        
        uploaded_files = st.file_uploader("Выберите файлы .xlsx", type=["xlsx", "xls"], 
                                          accept_multiple_files=True, key="compare_upload")
        
        if uploaded_files:
            compare_what = st.selectbox("Что сравнивать?", ["Деформация, μϵ", "Напряжение, МПа", "Частота, Гц"])
            fig_comp = go.Figure()
            
            for file in uploaded_files:
                try:
                    df_raw = pd.read_excel(file)
                    if len(df_raw.columns) >= 3:
                        df_comp = df_raw.iloc[:, :3].copy()
                        df_comp.columns = ['load', 'freq', 'temp']
                        ok, _, df_clean = DataProcessor.validate_data(df_comp)
                        if ok:
                            result_comp, _ = DataProcessor.process_strain_data(
                                df_clean, f0, t0, sensor_type, g_val, c_val
                            )
                            if result_comp is not None:
                                y_col = {'Деформация, μϵ': 'strain', 
                                        'Напряжение, МПа': 'stress_MPa', 
                                        'Частота, Гц': 'freq'}[compare_what]
                                fig_comp.add_trace(go.Scatter(
                                    x=result_comp['load'],
                                    y=result_comp[y_col],
                                    mode='lines+markers',
                                    name=file.name
                                ))
                except Exception as e:
                    st.warning(f"Ошибка обработки {file.name}: {e}")
            
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
    
    elif page == "Справка":
        st.markdown("## 📚 Справка и полезные ссылки")
        
        st.markdown("### 📖 Документация")
        st.markdown("""
        - [Руководство пользователя](https://example.com/user-guide)
        - [Техническая документация по датчикам](https://example.com/tech-docs)
        - [API Reference](https://example.com/api)
        """)
        
        st.markdown("### 📄 Руководства по датчикам")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **MAS-VWS-SM25H (длинная база)**
            - [Скачать PDF](https://www.masios.com/docs/MAS-VWS-SM25H.pdf)
            - [Страница продукта](https://www.masios.com/product/sm25h)
            
            **MAS-VWS-SM15 (короткая база)**
            - [Скачать PDF](https://www.masios.com/docs/MAS-VWS-SM15.pdf)
            - [Страница продукта](https://www.masios.com/product/sm15)
            """)
        with col2:
            st.markdown("""
            **MAS-VWE (давление грунта)**
            - [Скачать PDF](https://www.masios.com/docs/MAS-VWE.pdf)
            - [Страница продукта](https://www.masios.com/product/vwe)
            
            **MAS-HVLog-sf (ручной считыватель)**
            - [Скачать PDF](https://www.masios.com/docs/MAS-HVLog-sf.pdf)
            - [Страница продукта](https://www.masios.com/product/hvlog)
            """)
        
        st.markdown("### 📄 Статьи и публикации (ОБНОВЛЕНО)")
        st.markdown("""
        - [Мониторинг напряжений в грунтах](https://example.com/article1)
        - [Выбор тензодатчиков](https://example.com/article2)
        - [Обработка данных](https://example.com/article3)
        - [Датчики давления грунта — месдоза, и датчики деформаций — тензодатчики](https://geofundament.ru/datchiki-davlenija-grunta-mesdoza-i-datchiki-deformacij-tenzodatchiki/)
        """)
        
        st.markdown("### 🎥 Видео-материалы")
        st.markdown("""
        - [Как пользоваться приложением](https://example.com/video-tutorial)
        - [Обработка свайных испытаний](https://example.com/pile-test)
        - [Калибровка датчиков](https://example.com/calibration)
        """)
        
        st.markdown("### 📞 Контакты")
        st.markdown("""
        - **Email:** support@geofundament.ru
        - **Телефон:** +7 (495) 123-45-67
        - **Telegram:** @geofundament_bot
        """)
        
        st.markdown("### ℹ️ О приложении")
        st.markdown("""
        **Версия:** 2.0  
        **Разработчик:** Геофундамент  
        **Лицензия:** MIT  
        **Дата сборки:** 26.07.2026
        """)

if __name__ == "__main__":
    logging.basicConfig(filename=CONFIG["LOG_FILE"], level=logging.INFO)
    main()
