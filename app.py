import os
import re
import io
import tempfile
import pandas as pd
import numpy as np
from flask import Flask, request, render_template, send_file
from scipy.optimize import minimize
import plotly.graph_objs as go
import plotly.io as pio
import xlsxwriter
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'xlsx'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- Парсинг осадок ----------
def parse_settlements(df, coords):
    marks = df.iloc[:, 0].astype(str).tolist()
    for m in marks:
        if m not in coords:
            coords[m] = (35.23, 9.345)
    x = np.array([coords[m][0] for m in marks])
    y = np.array([coords[m][1] for m in marks])
    dates, angles = [], []
    for col in df.columns[1:]:
        match = re.search(r'(\d{2}\.\d{2}\.\d{4})', col)
        if match:
            try:
                date_label = pd.to_datetime(match.group(1), dayfirst=True).strftime('%Y-%m-%d')
            except:
                date_label = match.group(1)
        else:
            date_label = col
        dates.append(date_label)
        raw = df[col].values
        nums = []
        for v in raw:
            if isinstance(v, (int, float)):
                nums.append(float(v))
            elif isinstance(v, str):
                vc = v.replace(',', '.').strip()
                if vc in ('', '-', '—', 'нет доступа', 'новая', 'уничтожен', 'деформация'):
                    nums.append(np.nan)
                else:
                    try:
                        nums.append(float(vc))
                    except:
                        nums.append(np.nan)
            else:
                nums.append(np.nan)
        s_mm = np.array(nums)
        valid = ~np.isnan(s_mm)
        if np.sum(valid) < 3:
            angles.append((np.nan, np.nan))
            continue
        xv, yv, sv = x[valid], y[valid], s_mm[valid] / 1000.0
        def res(p):
            a, b, c = p
            return sv - (a*xv + b*yv + c)
        opt = minimize(lambda p: np.sum(res(p)**2), [0,0,0], method='Nelder-Mead')
        a, b, _ = opt.x
        angles.append((np.degrees(np.arctan(a)), np.degrees(np.arctan(b))))
    return dates, angles

# ---------- Обработка файла ----------
def process_excel(filepath):
    xl = pd.ExcelFile(filepath)
    sheets = xl.sheet_names
    settle_sheet = next((s for s in sheets if 'стилобат' in s.lower()), None)
    if settle_sheet is None:
        raise ValueError("Не найден лист с осадками стилобата.")
    df = pd.read_excel(filepath, sheet_name=settle_sheet, header=0)
    coords = {
        '1': (0.0, 0.0), '2': (70.46, 0.0), '3': (70.46, 18.69), '4': (0.0, 18.69),
        '5': (17.615, 18.69), '6': (35.23, 18.69), '7': (52.845, 18.69),
        '8': (70.46, 9.345), '9': (52.845, 0.0), '10': (35.23, 0.0),
        '11': (17.615, 0.0), '12': (0.0, 9.345), '13': (17.615, 9.345),
        '14': (52.845, 9.345)
    }
    dates, angles = parse_settlements(df, coords)

    # График
    fig = go.Figure()
    ax_clean = [a[0] if not np.isnan(a[0]) else None for a in angles]
    ay_clean = [a[1] if not np.isnan(a[1]) else None for a in angles]
    fig.add_trace(go.Scatter(x=dates, y=ax_clean, mode='lines+markers', name='Фундамент αx'))
    fig.add_trace(go.Scatter(x=dates, y=ay_clean, mode='lines+markers', name='Фундамент αy'))
    fig.update_layout(title='Углы наклона фундамента', xaxis_title='Дата', yaxis_title='Угол, °')

    # Excel-отчёт
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    ws = workbook.add_worksheet('Таблица')
    ws.write('A1', 'Дата'); ws.write('B1', 'αx, °'); ws.write('C1', 'αy, °')
    for i, (d, (ax, ay)) in enumerate(zip(dates, angles), start=2):
        ws.write(f'A{i}', d)
        ws.write(f'B{i}', ax if not np.isnan(ax) else None)
        ws.write(f'C{i}', ay if not np.isnan(ay) else None)
    # График в отдельный лист
    ws_chart = workbook.add_worksheet('График')
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        pio.write_image(fig, tmp.name, format='png', width=800, height=400)
        ws_chart.insert_image('A1', tmp.name, {'x_scale': 0.8, 'y_scale': 0.8})
        img_path = tmp.name
    workbook.close()
    os.unlink(img_path)
    output.seek(0)
    return output

# ---------- Маршруты ----------
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html', error='Файл не выбран')
        file = request.files['file']
        if file.filename == '':
            return render_template('index.html', error='Файл не выбран')
        if not allowed_file(file.filename):
            return render_template('index.html', error='Только .xlsx')
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            excel_data = process_excel(filepath)
        except Exception as e:
            return render_template('index.html', error=f'Ошибка: {str(e)}')
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
        return send_file(
            excel_data,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='отчет_углы_наклона.xlsx'
        )
    return render_template('index.html')

@app.route('/ping')
def ping():
    return "OK", 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')