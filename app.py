import os
import json
import gspread
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash

# --- KONFIGURASI APLIKASI FLASK ---
app = Flask(__name__)
# Kunci rahasia untuk sesi dan flash messages (Ganti dengan string random yang kuat!)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_sangat_tidak_aman') 

# --- KONFIGURASI GOOGLE SHEETS ---
# Ambil kredensial JSON dari environment variable (Render)
SERVICE_ACCOUNT_JSON = os.environ.get('SERVICE_ACCOUNT_JSON')
SHEET_TITLE = os.environ.get('SHEET_TITLE', 'Aplikasi Jajan Harian') # Ganti dengan nama Sheet Anda
WORKSHEET_NAME = os.environ.get('WORKSHEET_NAME', 'Pengeluaran') # Ganti dengan nama Worksheet Anda

gc = None
try:
    if SERVICE_ACCOUNT_JSON:
        # Menggunakan kredensial dari environment variable (Render)
        creds = json.loads(SERVICE_ACCOUNT_JSON)
        gc = gspread.service_account_from_dict(creds)
    else:
        # Opsi fallback (misalnya jika testing lokal dengan file credentials.json)
        # HANYA UNTUK TESTING LOKAL. Jangan gunakan ini di produksi.
        print("PERINGATAN: Menggunakan file 'credentials.json' lokal. Pastikan SERVICE_ACCOUNT_JSON diset di Render.")
        gc = gspread.service_account(filename='credentials.json')
    
    sh = gc.open(SHEET_TITLE)
    worksheet = sh.worksheet(WORKSHEET_NAME)

except Exception as e:
    print(f"ERROR: Gagal terhubung ke Google Sheets: {e}")
    worksheet = None

# --- FUNGSI UTILITY ---

def get_data_dataframe():
    """Mengambil semua data dari Sheets dan mengembalikannya sebagai Pandas DataFrame."""
    if not worksheet:
        return pd.DataFrame() # Mengembalikan DataFrame kosong jika koneksi gagal
    try:
        # Mengambil semua nilai sebagai list of lists
        data = worksheet.get_all_values()
        
        # Jika data kosong atau hanya header
        if not data or len(data) <= 1:
            # Sesuaikan headers dengan skema yang diharapkan (misalnya tanpa Kategori jika itu opsional)
            return pd.DataFrame(columns=['Tanggal', 'Metode', 'Nominal', 'Kategori', 'Catatan'])

        # Baris pertama adalah header
        headers = data[0]
        rows = data[1:]
        
        df = pd.DataFrame(rows, columns=headers)
        
        # Konversi tipe data
        df['Tanggal'] = pd.to_datetime(df['Tanggal'], errors='coerce')
        # Ganti semua nilai non-numerik di kolom Nominal menjadi 0 sebelum konversi
        df['Nominal'] = pd.to_numeric(df['Nominal'], errors='coerce').fillna(0).astype(int)

        # Menambahkan indeks baris Sheets (row index 2 adalah baris data pertama)
        df['row_index'] = range(2, len(df) + 2)
        
        return df.sort_values(by='Tanggal', ascending=False)
    
    except Exception as e:
        print(f"ERROR saat mengambil data dari Sheets: {e}")
        return pd.DataFrame()

def calculate_charts(df):
    """Menghitung data untuk chart mingguan dan bulanan."""
    if df.empty:
        return [], [], [], []

    # --- Chart Mingguan ---
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    
    # Filter data 7 hari terakhir (Minggu sampai Hari Ini)
    weekly_data = df[df['Tanggal'].dt.date >= start_of_week].copy()
    
    # Agregasi pengeluaran per hari
    weekly_summary = weekly_data.groupby(weekly_data['Tanggal'].dt.strftime('%a'))['Nominal'].sum().reindex(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], fill_value=0)
    
    weekly_labels = weekly_summary.index.tolist()
    weekly_data_values = weekly_summary.values.tolist()

    # --- Chart Bulanan ---
    df['BulanTahun'] = df['Tanggal'].dt.to_period('M')
    monthly_summary = df.groupby('BulanTahun')['Nominal'].sum().sort_index()
    
    monthly_labels = [period.strftime('%b %y') for period in monthly_summary.index]
    monthly_data_values = monthly_summary.values.tolist()
    
    return weekly_labels, weekly_data_values, monthly_labels, monthly_data_values

def calculate_totals(df):
    """Menghitung total pengeluaran harian dan mingguan."""
    if df.empty:
        return 0, 0

    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    
    # Total Harian
    df_today = df[df['Tanggal'].dt.date == today]
    total_harian = df_today['Nominal'].sum()

    # Total Mingguan (Minggu sampai Hari Ini)
    df_week = df[df['Tanggal'].dt.date >= start_of_week]
    total_mingguan = df_week['Nominal'].sum()
    
    return total_harian, total_mingguan

# --- RUTE FLASK ---

@app.route('/', methods=['GET', 'POST'])
def index():
    df = get_data_dataframe()
    
    if request.method == 'POST':
        # Mengambil data formulir, nominal diambil dari input hidden (nominal_clean)
        tanggal_str = request.form.get('tanggal')
        metode = request.form.get('metode')
        
        # MENGHAPUS: Kategori (atau set default kosong)
        # Jika kolom Kategori masih ada di Sheets, kita kirim string kosong
        kategori = request.form.get('kategori', '') 
        
        nominal_str = request.form.get('nominal') # Ini adalah nilai "clean" dari input hidden
        catatan = request.form.get('catatan', '')

        # 1. Validasi Input Dasar (Kategori TIDAK lagi wajib)
        if not (tanggal_str and metode and nominal_str):
             flash('⚠️ Semua field wajib (Tanggal, Nominal, Metode) harus diisi.', 'warning')
             return redirect(url_for('index'))

        try:
            nominal = int(nominal_str)
        except ValueError:
            flash('🚨 Nominal harus berupa angka.', 'danger')
            return redirect(url_for('index'))

        # 2. Validasi Batas Nominal (1000 - 200000)
        if not (1000 <= nominal <= 200000):
            flash('🚨 Nominal harus antara Rp 1.000 hingga Rp 200.000.', 'danger')
            return redirect(url_for('index'))
            
        # 3. Validasi Batas Tanggal (Mundur 2 hari, Maju 1 hari)
        try:
            tanggal_input = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            
            batas_bawah = today - timedelta(days=2)
            batas_atas = today + timedelta(days=1)
            
            if not (batas_bawah <= tanggal_input <= batas_atas):
                # Validasi backend dipertahankan
                return redirect(url_for('index'))
                
        except ValueError:
            flash('🚨 Format tanggal tidak valid.', 'danger')
            return redirect(url_for('index'))
            
        # 4. Menyimpan Data ke Google Sheets
        if worksheet:
            try:
                data_row = [
                    tanggal_str,
                    metode.lower(),
                    nominal,
                    kategori if kategori else '', # Kategori kosong dikirim jika tidak ada di form
                    catatan
                ]
                worksheet.append_row(data_row)
                flash('✅ Pengeluaran berhasil dicatat!', 'success')
            except Exception as e:
                flash(f'❌ Gagal menyimpan data ke Sheets. Cek koneksi API dan izin akses. Error: {e}', 'danger')
        else:
             flash('❌ Gagal menyimpan data: Koneksi ke Google Sheets tidak tersedia.', 'danger')
        
        return redirect(url_for('index'))

    # --- Bagian GET Request ---
    
    # Hitung data untuk chart dan total
    weekly_labels, weekly_data, monthly_labels, monthly_data = calculate_charts(df)
    total_harian, total_mingguan = calculate_totals(df)

    # Ambil 10 data terakhir untuk log
    pengeluaran_list = df.head(10).to_dict('records')

    # Siapkan data untuk template
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # Batas tanggal
    batas_atas_str = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
    batas_bawah_str = (datetime.now().date() - timedelta(days=2)).strftime('%Y-%m-%d')

    return render_template('index.html', 
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
                           total_mingguan=total_mingguan)


@app.route('/delete', methods=['POST'])
def delete_entry():
    """Rute untuk menghapus baris data berdasarkan row_index."""
    row_index_str = request.form.get('row_index')

    if not worksheet or not row_index_str:
        flash('❌ Gagal menghapus data: Koneksi Sheets atau indeks tidak ditemukan.', 'danger')
        return redirect(url_for('index'))
    
    try:
        # row_index adalah nomor baris di Google Sheets
        row_index = int(row_index_str)
        
        # Validasi sederhana agar tidak menghapus header atau row yang tidak wajar
        if row_index < 2:
            flash('🚨 Indeks baris tidak valid untuk dihapus.', 'warning')
            return redirect(url_for('index'))
        
        # Hapus baris dari Sheets
        worksheet.delete_rows(row_index)
        flash('🗑️ Pengeluaran berhasil dihapus.', 'info')
        
    except ValueError:
        flash('🚨 Indeks baris tidak valid (harus angka).', 'danger')
    except Exception as e:
        flash(f'❌ Terjadi kesalahan saat menghapus data: {e}', 'danger')

    return redirect(url_for('index'))


if __name__ == '__main__':
    # Pastikan untuk mengganti '0.0.0.0' jika Anda menjalankan di lokal dan mengalami isu
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))