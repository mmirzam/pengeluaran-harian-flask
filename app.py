from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
import gspread
import pandas as pd
import calendar
import os
import json

app = Flask(__name__)
# Diperlukan untuk Flash Messages dan Sesi
app.secret_key = 'kunci_rahasia_dan_acak_untuk_flask' 

# --- Konfigurasi Google Sheets ---
SERVICE_ACCOUNT_FILE = 'service-account-key.json' 
SHEET_NAME = 'Pengeluaran Harian Data' 

def get_gspread_client():
    """Mendapatkan klien gspread menggunakan kredensial JSON (lokal atau dari ENV)."""
    json_creds = os.environ.get('SERVICE_ACCOUNT_JSON')
    
    if json_creds:
        try:
            # Mengambil kredensial dari environment variable (untuk deployment seperti Render)
            cleaned_creds = json_creds.strip().replace('\\\\n', '\\n') 
            
            creds = json.loads(cleaned_creds)
            gc = gspread.service_account_from_dict(creds)
        except Exception as e:
            print(f"ERROR: Failed to load JSON from ENV: {e}")
            flash(f'🚨 Koneksi Google Sheets GAGAL! (Gagal load kunci dari ENV: {e})', 'danger')
            raise 
    else:
        try:
            # Menggunakan file lokal (untuk local development)
            with open(SERVICE_ACCOUNT_FILE, 'r') as f:
                creds = json.load(f)
            gc = gspread.service_account_from_dict(creds)
        except FileNotFoundError:
            print(f"ERROR: Credentials file {SERVICE_ACCOUNT_FILE} not found.")
            raise
        except Exception as e:
            print(f"ERROR: Failed to load/read local JSON credentials: {e}")
            raise
    
    return gc

def get_data_from_sheet():
    """Mengambil semua data dari sheet dan mengkonversinya ke DataFrame."""
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SHEET_NAME)
        worksheet = spreadsheet.sheet1 
        
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        
        if df.empty:
            return pd.DataFrame({'Tanggal': [], 'Metode': [], 'Nominal': [], 'Catatan': []})
            
        df = df.copy() 
        df['Tanggal'] = pd.to_datetime(df['Tanggal'], errors='coerce')
        df['Nominal'] = pd.to_numeric(df['Nominal'], errors='coerce').fillna(0).astype(int) 
        df = df.dropna(subset=['Tanggal'])
        
        return df.sort_values(by='Tanggal', ascending=False)
    except Exception as e:
        print(f"ERROR: Failed to connect/read Google Sheets: {e}")
        flash(f'🚨 Koneksi Google Sheets GAGAL! ({e})', 'danger') 
        return pd.DataFrame() 

# --- FUNGSI CHART ---

def get_weekly_data(df):
    """Menghitung pengeluaran harian untuk 7 hari terakhir (dari DataFrame)."""
    if df.empty: return [0]*7, ["" for _ in range(7)]
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=6)
    df_filtered = df[(df['Tanggal'].dt.date >= seven_days_ago)].copy()
    daily_expense = df_filtered.groupby(df_filtered['Tanggal'].dt.date)['Nominal'].sum()
    dates = [seven_days_ago + timedelta(days=i) for i in range(7)]
    labels = [d.strftime('%a, %d/%m') for d in dates]
    chart_data = [int(daily_expense.get(d, 0)) for d in dates] 
    return chart_data, labels

def get_monthly_data(df):
    """Menghitung pengeluaran bulanan untuk 6 bulan terakhir (dari DataFrame)."""
    if df.empty: return [0]*6, ["" for _ in range(6)]
    df = df.copy() 
    df['MonthYear'] = df['Tanggal'].dt.to_period('M')
    monthly_expense = df.groupby('MonthYear')['Nominal'].sum()
    labels = []
    chart_data = []
    today_period = pd.Period(datetime.now(), freq='M')
    for i in range(5, -1, -1):
        target_period = today_period - i
        month_name = calendar.month_name[target_period.month]
        label = f"{month_name} {target_period.year}"
        labels.append(label)
        data = monthly_expense.get(target_period, 0)
        chart_data.append(int(data)) 
    return chart_data, labels

# --- ROUTING ---

@app.route('/', methods=['GET', 'POST'])
def index():
    df = get_data_from_sheet()

    if request.method == 'POST':
        try:
            tanggal_str = request.form.get('tanggal')
            metode = request.form.get('metode')
            nominal_str = request.form.get('nominal')
            catatan = request.form.get('catatan')
            
            # --- VALIDASI NOMINAL & TANGGAL (BACKEND - LAPISAN KEAMANAN) ---
            
            # 1. Validasi Nominal (1000 - 200000)
            if not nominal_str:
                flash('⚠️ Nominal tidak boleh kosong!', 'warning')
                return redirect(url_for('index'))
                
            nominal = int(nominal_str)
            if not (1000 <= nominal <= 200000):
                flash('🚨 Nominal harus antara Rp 1.000 hingga Rp 200.000.', 'danger')
                return redirect(url_for('index'))

            # 2. Validasi Batas Tanggal (Mundur 2 hari, Maju 1 hari)
            tanggal_input = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            batas_bawah = today - timedelta(days=2)
            batas_atas = today + timedelta(days=1)
            
            # Jika validasi tanggal GAGAL di backend, berikan flash message
            if not (batas_bawah <= tanggal_input <= batas_atas):
                tgl_bawah_fmt = batas_bawah.strftime('%d/%m/%Y')
                tgl_atas_fmt = batas_atas.strftime('%d/%m/%Y')
                flash(f'🗓️ Tanggal tidak valid! Harus antara {tgl_bawah_fmt} dan {tgl_atas_fmt}.', 'danger')
                return redirect(url_for('index'))
            
            # --- END VALIDASI BARU ---

            new_row = [tanggal_str, metode, nominal, catatan]
            
            # Tulis ke Google Sheets
            gc = get_gspread_client()
            spreadsheet = gc.open(SHEET_NAME)
            worksheet = spreadsheet.sheet1
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            
            flash(f'✅ Pengeluaran Rp {nominal:,.0f} berhasil dicatat!', 'success')
            return redirect(url_for('index'))
        
        except ValueError:
            flash('🚨 Nominal atau Tanggal tidak valid.', 'danger')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"Error saat menyimpan data: {e}")
            flash(f'❌ Gagal menyimpan data: {e}', 'danger')
            return redirect(url_for('index'))

    # Siapkan data untuk chart dan display
    chart_data_mingguan, chart_labels_mingguan = get_weekly_data(df)
    chart_data_bulanan, chart_labels_bulanan = get_monthly_data(df)
    
    if not df.empty:
        df_display = df.head(10).copy()
        if pd.api.types.is_datetime64_any_dtype(df_display['Tanggal']):
            df_display['Tanggal'] = df_display['Tanggal'].dt.strftime('%Y-%m-%d')
        pengeluaran_list = df_display.to_dict('records')
    else:
        pengeluaran_list = []

    # Kita mengirim batas MIN dan MAX ke template
    batas_atas_str = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d') # T + 1 hari
    batas_bawah_str = (datetime.now().date() - timedelta(days=2)).strftime('%Y-%m-%d') # T - 2 hari

    return render_template('index.html', 
                           pengeluaran_list=pengeluaran_list,
                           chart_data_mingguan=chart_data_mingguan,
                           chart_labels_mingguan=chart_labels_mingguan,
                           chart_data_bulanan=chart_data_bulanan,
                           chart_labels_bulanan=chart_labels_bulanan,
                           current_date=datetime.now().strftime('%Y-%m-%d'),
                           batas_nominal_max=200000,
                           batas_nominal_min=1000,
                           batas_tanggal_max=batas_atas_str,
                           batas_tanggal_min=batas_bawah_str # VARIABEL BARU
                           )

if __name__ == '__main__':
    app.run(debug=True)
