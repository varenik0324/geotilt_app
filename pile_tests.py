import pandas as pd
import numpy as np
import re
from io import BytesIO
import xlsxwriter
import plotly.graph_objects as go

# Константы калибровки (по умолчанию, могут переопределяться из файла)
DEFAULT_A = 6.51e-08
DEFAULT_B = -0.02931
DEFAULT_C = 248.4372
DEFAULT_K = -0.036375
DEFAULT_T_REF = 23.9
DEFAULT_G = 0.028418   # psi/digit (не используется в формуле, но оставлено)

def parse_pile_data(file_bytes):
    """
    Основная функция парсинга и расчёта.
    Возвращает словарь с результатами: {датчик: DataFrame}
    """
    xl = pd.ExcelFile(file_bytes)
    sheet_names = xl.sheet_names

    # Ищем лист с нулевыми значениями (обычно первый лист с "Свая")
    zero_sheet = None
    test_sheet = None
    for name in sheet_names:
        if 'свая' in name.lower() or 'нулевой' in name.lower():
            zero_sheet = name
        if 'испытания' in name.lower():
            test_sheet = name

    if zero_sheet is None:
        # Попробуем найти лист, где есть "Частота" и "Температура"
        for name in sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=name, header=None)
            # Ищем строку с "Частота" и "Температура"
            for idx, row in df.iterrows():
                if any('Частота' in str(cell) for cell in row) and any('Температура' in str(cell) for cell in row):
                    zero_sheet = name
                    break
            if zero_sheet:
                break

    if test_sheet is None:
        # Ищем лист, где есть "Нагрузка" и "Давление"
        for name in sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=name, header=None)
            for idx, row in df.iterrows():
                if any('Нагрузка' in str(cell) for cell in row) and any('Давление' in str(cell) for cell in row):
                    test_sheet = name
                    break
            if test_sheet:
                break

    # Если не нашли отдельные листы, возможно, всё в одном листе
    if zero_sheet is None and test_sheet is None:
        # Попробуем прочитать первый лист как единый
        df = pd.read_excel(file_bytes, sheet_name=0, header=None)
        # Ищем структуру: нулевые значения в верхней части, испытания в нижней
        # Это сложно, упростим: будем искать строки с "Цикл" и "Ступень"
        # В реальном коде можно реализовать более сложную логику
        raise ValueError("Не удалось определить структуру файла. Убедитесь, что есть листы с нулевыми данными и испытаниями.")

    # Парсим нулевые значения
    df_zero = pd.read_excel(file_bytes, sheet_name=zero_sheet, header=None)
    zero_data = {}
    # Ищем заголовки: № датчика, Частота, Температура
    # Обычно структура: строки с номерами датчиков, потом значения
    # Определим начало данных
    start_row = None
    for idx, row in df_zero.iterrows():
        if any('№ датчика' in str(cell) for cell in row):
            start_row = idx + 1
            break
    if start_row is None:
        # Если не нашли, попробуем искать по числовым значениям
        for idx, row in df_zero.iterrows():
            if isinstance(row[0], (int, float)) and row[0] in [1, 2, 3, '1-й верх', '2-й верх']:
                start_row = idx
                break
    if start_row is None:
        start_row = 0

    # Определим столбцы: частота и температура обычно в 2-м и 3-м столбцах (индексы 1 и 2)
    # Но может быть по-разному. Используем поиск по заголовкам.
    # Просто переберем строки и соберем данные
    current_sensor = None
    for idx in range(start_row, len(df_zero)):
        row = df_zero.iloc[idx]
        if pd.isna(row[0]) or (isinstance(row[0], str) and 'уровень' in row[0].lower()):
            # Это может быть заголовок уровня, пропускаем
            continue
        # Попробуем извлечь частоту и температуру
        freq = None
        temp = None
        # Ищем числовые значения
        for val in row:
            if isinstance(val, (int, float)):
                if freq is None:
                    freq = val
                elif temp is None:
                    temp = val
        if freq is not None and temp is not None:
            # Определяем имя датчика
            sensor_name = str(row[0]).strip()
            if sensor_name and sensor_name not in ['Верх сваи', 'Низ сваи', 'Под пятой']:
                zero_data[sensor_name] = {'f0': freq, 'T0': temp}

    # Парсим данные испытаний
    df_test = pd.read_excel(file_bytes, sheet_name=test_sheet, header=None)
    # Ищем строки с "Ступень", чтобы определить начало колонок
    # Также ищем строки с датчиками (1-й верх, 2-й верх, ...)
    # Сложная структура: ступени по горизонтали, датчики по вертикали.
    # Лучше использовать поиск по ключевым словам в заголовках.
    # Соберем все данные в список словарей
    test_data = []
    # Найдем строку, где есть "Время", "Нагрузка", "Давление", "Частота", "Температура"
    header_row = None
    for idx, row in df_test.iterrows():
        row_str = ' '.join(str(cell) for cell in row if pd.notna(cell))
        if 'Время' in row_str and 'Нагрузка' in row_str and 'Давление' in row_str:
            header_row = idx
            break
    if header_row is None:
        raise ValueError("Не удалось найти заголовки столбцов в листе испытаний.")

    # Определим индексы столбцов для каждой ступени
    # Заголовки могут повторяться через каждые 5 столбцов: Время, Нагрузка, Давление, Частота, Температура
    # Пропарсим строку заголовка, чтобы создать карту
    headers = df_test.iloc[header_row].tolist()
    # Приведем к строковому виду
    headers = [str(h).strip() if pd.notna(h) else '' for h in headers]
    # Найдем группы по "Ступень"
    step_columns = {}
    current_step = None
    for i, h in enumerate(headers):
        if 'Ступень' in h:
            # Новая ступень
            step_match = re.search(r'Ступень\s*(\d+)', h)
            if step_match:
                current_step = int(step_match.group(1))
                step_columns[current_step] = {'start': i, 'columns': {}}
        elif current_step is not None and h:
            # Если мы внутри ступени, запоминаем индексы нужных колонок
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

    # Теперь пройдем по строкам с данными датчиков (ниже заголовка)
    sensor_start = header_row + 1
    # Будем искать строки, где первый столбец содержит имя датчика (1-й верх, 2-й верх, ...)
    sensors = []
    for idx in range(sensor_start, len(df_test)):
        row = df_test.iloc[idx]
        first_cell = str(row[0]).strip()
        if first_cell and re.match(r'\d+-?[й]?\s*(верх|сред|низ)', first_cell, re.IGNORECASE):
            sensors.append(idx)

    # Для каждого датчика извлекаем данные по всем ступеням
    results = {}
    for idx in sensors:
        sensor_name = str(df_test.iloc[idx, 0]).strip()
        # Создаем DataFrame для этого датчика
        rows = []
        for step, cols in step_columns.items():
            # Проверяем, что все нужные колонки есть
            if 'Время' not in cols or 'Нагрузка' not in cols or 'Давление' not in cols:
                continue
            # Извлекаем значения из строки датчика
            row_data = df_test.iloc[idx]
            time_val = row_data[cols['Время']] if cols['Время'] is not None else None
            load_val = row_data[cols['Нагрузка']] if cols['Нагрузка'] is not None else None
            press_val = row_data[cols['Давление']] if cols['Давление'] is not None else None
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
            # Добавим нулевые значения, если они есть
            if sensor_name in zero_data:
                f0 = zero_data[sensor_name]['f0']
                T0 = zero_data[sensor_name]['T0']
                # Рассчитаем давление по формуле, если есть частота и температура
                # Но в данных испытаний частота и температура часто пустые, можно оставить как есть
                # Для расчета используем формулу
                df_sensor['Давление_расч, Psi'] = np.nan
                df_sensor['Давление_расч, МПа'] = np.nan
                for i, row in df_sensor.iterrows():
                    f = row['Частота, Гц']
                    T = row['Температура, °С']
                    if pd.notna(f) and pd.notna(T):
                        Psi = DEFAULT_A * (f**2) + DEFAULT_B * f + DEFAULT_C + DEFAULT_K * (T - DEFAULT_T_REF)
                        df_sensor.at[i, 'Давление_расч, Psi'] = Psi
                        df_sensor.at[i, 'Давление_расч, МПа'] = Psi * 0.00689475729317831
                results[sensor_name] = df_sensor
            else:
                results[sensor_name] = df_sensor

    return results