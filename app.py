import os
import json
import gspread
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash

# --- KONFIGURASI APLIKASI FLASK ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_sangat_tidak_aman') 

# --- KONFIGURASI GOOGLE SHEETS ---
SERVICE_ACCOUNT_JSON = os.environ.get('SERVICE_ACCOUNT_JSON')
SHEET_TITLE = os.environ.get('SHEET_TITLE', 'Aplikasi Jajan Harian')
WORKSHEET_EXPENSE = os.environ.get('WORKSHEET_EXPENSE', 'Pengeluaran')
WORKSHEET_INCOME = os.environ.get('WORKSHEET_INCOME', 'Pemasukan')

gc = None
worksheet_expense = None
worksheet_income = None

try:
    if SERVICE_ACCOUNT_JSON:
        creds = json.loads(SERVICE_ACCOUNT_JSON)
        gc = gspread.service_account_from_dict(creds)
    else:
        gc = gspread.service_account(filename='service-account-key.json')
    
    sh = gc.open(SHEET_TITLE)
    worksheet_expense = sh.worksheet(WORKSHEET_EXPENSE)
    worksheet_income = sh.worksheet(WORKSHEET_INCOME)

except Exception as e:
    print(f"ERROR: Gagal terhubung ke Google Sheets: {e}")
    worksheet_expense = None
    worksheet_income = None


# --- FUNGSI UTILITY ---

def safe_to_date(series):
    return series.apply(lambda x: x.to_pydatetime().date() if pd.notnull(x) else None)

def get_data_dataframe(worksheet):
    if not worksheet:
        return pd.DataFrame()
    try:
        data = worksheet.get_all_values()
        if not data or len(data) <= 1:
            if worksheet.title == WORKSHEET_INCOME:
                return pd.DataFrame(columns=['Tanggal', 'Modal', 'Jual', 'Via', 'Catatan'])
            else:
                return pd.DataFrame(columns=['Tanggal', 'Metode', 'Nominal', 'Catatan'])

        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)

        df['Tanggal'] = pd.to_datetime(df['Tanggal'], errors='coerce')
        df.dropna(subset=['Tanggal'], inplace=True)
        
        if worksheet.title == WORKSHEET_INCOME:
            df['Modal'] = pd.to_numeric(df['Modal'], errors='coerce').fillna(0).astype(int)
            df['Jual'] = pd.to_numeric(df['Jual'], errors='coerce').fillna(0).astype(int)
            df['Profit'] = (df['Jual'] - df['Modal']).astype(int)
            df['Nominal'] = df['Profit']
        else:
            df['Nominal'] = pd.to_numeric(df['Nominal'], errors='coerce').fillna(0).astype(int)

        df['row_index'] = range(2, len(df) + 2)
        df_sorted = df.sort_values(by='Tanggal', ascending=False).copy()
        return df_sorted
    except Exception as e:
        print(f"ERROR saat mengambil data dari Sheets ({worksheet.title}): {e}")
        return pd.DataFrame()

def calculate_charts(df):
    if df.empty:
        return [], [], [], []
    today = datetime.now().date()
    df['date_only'] = safe_to_date(df['Tanggal']) 
    start_of_week = today - timedelta(days=today.weekday())
    
    weekly_data = df[df['date_only'] >= start_of_week].copy()
    weekly_summary = weekly_data.groupby(weekly_data['Tanggal'].dt.dayofweek)['Nominal'].sum()
    day_map = {0: 'Sen', 1: 'Sel', 2: 'Rab', 3: 'Kam', 4: 'Jum', 5: 'Sab', 6: 'Min'}
    full_week_summary = weekly_summary.reindex(range(7), fill_value=0)
    weekly_labels = [day_map[i] for i in full_week_summary.index.tolist()]
    weekly_data_values = [int(val) for val in full_week_summary.values.tolist()]

    df['BulanTahun'] = df['Tanggal'].dt.to_period('M')
    monthly_summary = df.groupby('BulanTahun')['Nominal'].sum().sort_index()
    monthly_labels = [period.strftime('%b %y') for period in monthly_summary.index]
    monthly_data_values = [int(val) for val in monthly_summary.values.tolist()]
    return weekly_labels, weekly_data_values, monthly_labels, monthly_data_values

def calculate_totals(df):
    if df.empty:
        return 0, 0
    today = datetime.now().date()
    df['date_only'] = safe_to_date(df['Tanggal']) 
    start_of_week = today - timedelta(days=today.weekday())
    total_harian = int(df[df['date_only'] == today]['Nominal'].sum())
    total_mingguan = int(df[df['date_only'] >= start_of_week]['Nominal'].sum())
    return total_harian, total_mingguan


# --- ROUTES ---

@app.route('/')
def home():
    # Default redirect ke halaman pengeluaran
    return redirect(url_for('pengeluaran_index'))

@app.route('/pengeluaran', methods=['GET', 'POST'])
def pengeluaran_index():
    df = get_data_dataframe(worksheet_expense)
    
    if request.method == 'POST':
        tanggal_str = request.form.get('tanggal')
        metode = request.form.get('metode')
        nominal_str = request.form.get('nominal')
        catatan = request.form.get('catatan', '')
        
        if not (tanggal_str and metode and nominal_str):
            flash('⚠️ Semua field wajib diisi.', 'warning')
            return redirect(url_for('pengeluaran_index'))

        try:
            nominal = int(nominal_str)
        except ValueError:
            flash('🚨 Nominal harus berupa angka.', 'danger')
            return redirect(url_for('pengeluaran_index'))

        if not (1000 <= nominal <= 200000):
            flash('🚨 Nominal harus antara Rp 1.000 hingga Rp 200.000.', 'danger')
            return redirect(url_for('pengeluaran_index'))

        try:
            tanggal_input = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            if not (today - timedelta(days=2) <= tanggal_input <= today + timedelta(days=1)):
                flash('🚨 Tanggal harus dalam rentang H-2 sampai H+1.', 'danger')
                return redirect(url_for('pengeluaran_index'))
        except ValueError:
            flash('🚨 Format tanggal tidak valid.', 'danger')
            return redirect(url_for('pengeluaran_index'))

        if worksheet_expense:
            try:
                worksheet_expense.append_row([tanggal_str, metode.lower(), nominal, catatan]) 
                flash('✅ Pengeluaran berhasil dicatat!', 'success')
            except Exception as e:
                flash(f'❌ Gagal menyimpan data Pengeluaran: {e}', 'danger')
        else:
            flash('❌ Koneksi ke Google Sheets tidak tersedia.', 'danger')
        return redirect(url_for('pengeluaran_index'))

    weekly_labels, weekly_data, monthly_labels, monthly_data = calculate_charts(df)
    total_harian, total_mingguan = calculate_totals(df)
    pengeluaran_list = df.head(10).to_dict('records')
    for item in pengeluaran_list:
        if isinstance(item.get('Tanggal'), pd.Timestamp):
            item['Tanggal'] = item['Tanggal'].strftime('%Y-%m-%d')
        if item.get('Nominal') is not None:
            item['Nominal'] = int(item['Nominal'])

    current_date = datetime.now().strftime('%Y-%m-%d')
    batas_atas_str = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
    batas_bawah_str = (datetime.now().date() - timedelta(days=2)).strftime('%Y-%m-%d')

    return render_template("index.html",
                           tab_active='pengeluaran',
                           current_date=current_date,
                           pengeluaran_list=pengeluaran_list,
                           chart_labels_mingguan=weekly_labels,
                           chart_data_mingguan=weekly_data,
                           chart_labels_bulanan=monthly_labels,
                           chart_data_bulanan=monthly_data,
                           batas_nominal_max=200000,
                           batas_nominal_min=1000,
                           batas_tanggal_max=batas_atas_str,
                           batas_tanggal_min=batas_bawah_str,
                           total_harian=total_harian,
                           total_mingguan=total_mingguan,
                           total_harian_profit=0,
                           total_mingguan_profit=0,
                           chart_labels_mingguan_inc=[],
                           chart_data_mingguan_inc=[],
                           chart_labels_bulanan_inc=[],
                           chart_data_bulanan_inc=[],
                           batas_nominal_min_inc=10000)

@app.route('/pemasukan', methods=['GET', 'POST'])
def pemasukan_index():
    df = get_data_dataframe(worksheet_income)
    
    if request.method == 'POST':
        tanggal_str = request.form.get('tanggal')
        modal_str = request.form.get('modal')
        jual_str = request.form.get('jual')
        via = request.form.get('via')
        catatan = request.form.get('catatan', '')

        if not (tanggal_str and modal_str and jual_str and via):
            flash('⚠️ Semua field wajib diisi.', 'warning')
            return redirect(url_for('pemasukan_index'))

        try:
            modal = int(modal_str)
            jual = int(jual_str)
        except ValueError:
            flash('🚨 Modal & Jual harus angka.', 'danger')
            return redirect(url_for('pemasukan_index'))

        if not (modal >= 10000 and jual >= 10000):
            flash('🚨 Minimal Rp 10.000.', 'danger')
            return redirect(url_for('pemasukan_index'))

        try:
            tanggal_input = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            if not (today - timedelta(days=2) <= tanggal_input <= today + timedelta(days=1)):
                flash('🚨 Tanggal harus dalam rentang H-2 sampai H+1.', 'danger')
                return redirect(url_for('pemasukan_index'))
        except ValueError:
            flash('🚨 Format tanggal tidak valid.', 'danger')
            return redirect(url_for('pemasukan_index'))

        if worksheet_income:
            try:
                worksheet_income.append_row([tanggal_str, modal, jual, via.lower(), catatan])
                flash('✅ Pemasukan berhasil dicatat!', 'success')
            except Exception as e:
                flash(f'❌ Gagal menyimpan data Pemasukan: {e}', 'danger')
        else:
            flash('❌ Koneksi ke Google Sheets tidak tersedia.', 'danger')
        return redirect(url_for('pemasukan_index'))

    weekly_labels, weekly_data, monthly_labels, monthly_data = calculate_charts(df)
    total_harian_profit, total_mingguan_profit = calculate_totals(df)
    pemasukan_list = df.head(10).to_dict('records')
    for item in pemasukan_list:
        if isinstance(item.get('Tanggal'), pd.Timestamp):
            item['Tanggal'] = item['Tanggal'].strftime('%Y-%m-%d')
        if item.get('Modal') is not None:
            item['Modal'] = int(item['Modal'])
        if item.get('Jual') is not None:
            item['Jual'] = int(item['Jual'])
        if item.get('Profit') is not None:
            item['Profit'] = int(item['Profit'])

    current_date = datetime.now().strftime('%Y-%m-%d')
    batas_atas_str = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
    batas_bawah_str = (datetime.now().date() - timedelta(days=2)).strftime('%Y-%m-%d')

    return render_template("index.html",
                           tab_active='pemasukan',
                           current_date=current_date,
                           pemasukan_list=pemasukan_list,
                           chart_labels_mingguan_inc=weekly_labels,
                           chart_data_mingguan_inc=weekly_data,
                           chart_labels_bulanan_inc=monthly_labels,
                           chart_data_bulanan_inc=monthly_data,
                           batas_nominal_min_inc=10000,
                           batas_tanggal_max=batas_atas_str,
                           batas_tanggal_min=batas_bawah_str,
                           total_harian_profit=total_harian_profit,
                           total_mingguan_profit=total_mingguan_profit,
                           total_harian=0,
                           total_mingguan=0,
                           chart_labels_mingguan=[],
                           chart_data_mingguan=[],
                           chart_labels_bulanan=[],
                           chart_data_bulanan=[],
                           batas_nominal_max=200000,
                           batas_nominal_min=1000)

@app.route('/delete', methods=['POST'])
def delete_entry():
    row_index_str = request.form.get('row_index')
    tab_type = request.form.get('tab_type')
    worksheet_to_use = None
    redirect_route = 'pengeluaran_index'
    log_name = ''

    if tab_type == 'pengeluaran':
        worksheet_to_use = worksheet_expense
        redirect_route = 'pengeluaran_index'
        log_name = 'Pengeluaran'
    elif tab_type == 'pemasukan':
        worksheet_to_use = worksheet_income
        redirect_route = 'pemasukan_index'
        log_name = 'Pemasukan'
    else:
        flash('❌ Jenis tab tidak dikenal.', 'danger')
        return redirect(url_for('pengeluaran_index'))

    if not worksheet_to_use or not row_index_str:
        flash(f'❌ Gagal menghapus data {log_name}.', 'danger')
        return redirect(url_for(redirect_route))

    try:
        row_index = int(row_index_str)
        if row_index < 2:
            flash('🚨 Indeks baris tidak valid.', 'warning')
            return redirect(url_for(redirect_route)) 
        worksheet_to_use.delete_rows(row_index)
        flash(f'🗑️ Data {log_name} berhasil dihapus.', 'info')
    except Exception as e:
        flash(f'❌ Terjadi kesalahan: {e}', 'danger')

    return redirect(url_for(redirect_route))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
