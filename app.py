from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
import gspread
import pandas as pd
import calendar
import os
import json

app = Flask(__name__)
# 1. TAMBAH SECRET KEY: Diperlukan untuk Flash Messages dan Sesi
app.secret_key = 'kunci_rahasia_dan_acak_untuk_flask' 

# --- Konfigurasi Google Sheets ---
SERVICE_ACCOUNT_FILE = 'service-account-key.json' 
SHEET_NAME = 'Pengeluaran Harian Data' 

# Fungsi untuk mendapatkan klien gspread (aman untuk Local & Render)
def get_gspread_client():
    """Mendapatkan klien gspread menggunakan kredensial JSON (lokal atau dari ENV)."""
    json_creds = os.environ.get('SERVICE_ACCOUNT_JSON')
    
    if json_creds:
        try:
            creds = json.loads(json_creds)
            gc = gspread.service_account_from_dict(creds)
        except Exception as e:
            print(f"ERROR: Failed to load JSON from ENV: {e}")
            raise 
    else:
        try:
            # Menggunakan json.load dan service_account_from_dict lebih stabil
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
        # Fix: Konversi Nominal ke int standar Python
        df['Nominal'] = pd.to_numeric(df['Nominal'], errors='coerce').fillna(0).astype(int) 
        df = df.dropna(subset=['Tanggal'])
        
        return df.sort_values(by='Tanggal', ascending=False)
    except Exception as e:
        print(f"ERROR: Failed to connect/read Google Sheets: {e}")
        flash(f'🚨 Koneksi Google Sheets GAGAL! ({e})', 'danger')
        return pd.DataFrame() 

# --- FUNGSI CHART (Dengan Perbaikan int64) ---

def get_weekly_data(df):
    """Menghitung pengeluaran harian untuk 7 hari terakhir (dari DataFrame)."""
    if df.empty: return [0]*7, ["" for _ in range(7)]
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=6)
    df_filtered = df[(df['Tanggal'].dt.date >= seven_days_ago)].copy()
    daily_expense = df_filtered.groupby(df_filtered['Tanggal'].dt.date)['Nominal'].sum()
    dates = [seven_days_ago + timedelta(days=i) for i in range(7)]
    labels = [d.strftime('%a, %d/%m') for d in dates]
    # Fix: Konversi ke int() standar Python
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
        # Fix: Konversi ke int() standar Python
        chart_data.append(int(data)) 
    return chart_data, labels

# --- ROUTING ---

@app.route('/', methods=['GET', 'POST'])
def index():
    df = get_data_from_sheet()

    if request.method == 'POST':
        try:
            tanggal = request.form.get('tanggal')
            metode = request.form.get('metode')
            
            # Validasi Nominal
            nominal_str = request.form.get('nominal')
            if not nominal_str:
                 flash('⚠️ Nominal tidak boleh kosong!', 'warning')
                 return redirect(url_for('index'))
                 
            nominal = int(nominal_str) # Ini akan raise ValueError jika bukan angka
            catatan = request.form.get('catatan')
            new_row = [tanggal, metode, nominal, catatan]
            
            # Tulis ke Google Sheets
            gc = get_gspread_client()
            spreadsheet = gc.open(SHEET_NAME)
            worksheet = spreadsheet.sheet1
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            
            # 2. PANGGIL FLASH: Kirim pesan sukses ke template
            flash(f'✅ Pengeluaran Rp {nominal:,.0f} berhasil dicatat!', 'success')
            
            # 3. REDIRECT: Wajib setelah flash
            return redirect(url_for('index'))
        
        except ValueError:
            flash('🚨 Nominal harus berupa angka yang valid!', 'danger')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"Error saat menyimpan data: {e}")
            flash('❌ Gagal menyimpan data. Cek input dan log server.', 'danger')
            return redirect(url_for('index'))

    # Siapkan data untuk chart dan display
    chart_data_mingguan, chart_labels_mingguan = get_weekly_data(df)
    chart_data_bulanan, chart_labels_bulanan = get_monthly_data(df)
    
    # Tampilkan 10 pengeluaran terakhir
    if not df.empty:
        df_display = df.head(10).copy()
        
        # Fix: Periksa tipe data sebelum memanggil .dt.strftime
        if pd.api.types.is_datetime64_any_dtype(df_display['Tanggal']):
            df_display['Tanggal'] = df_display['Tanggal'].dt.strftime('%Y-%m-%d')
        
        pengeluaran_list = df_display.to_dict('records')
    else:
        pengeluaran_list = []

    return render_template('index.html', 
                           pengeluaran_list=pengeluaran_list,
                           chart_data_mingguan=chart_data_mingguan,
                           chart_labels_mingguan=chart_labels_mingguan,
                           chart_data_bulanan=chart_data_bulanan,
                           chart_labels_bulanan=chart_labels_bulanan,
                           current_date=datetime.now().strftime('%Y-%m-%d'))

if __name__ == '__main__':
    app.run(debug=True)