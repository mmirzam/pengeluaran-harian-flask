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
SERVICE_ACCOUNT_JSON = os.environ.get('SERVICE_ACCOUNT_JSON')
SHEET_TITLE = os.environ.get('SHEET_TITLE', 'Aplikasi Jajan Harian')
# Nama Worksheet default
WORKSHEET_EXPENSE = os.environ.get('WORKSHEET_EXPENSE', 'Pengeluaran')
WORKSHEET_INCOME = os.environ.get('WORKSHEET_INCOME', 'Pemasukan') # Worksheet Baru

gc = None
worksheet_expense = None
worksheet_income = None

try:
    if SERVICE_ACCOUNT_JSON:
        creds = json.loads(SERVICE_ACCOUNT_JSON)
        gc = gspread.service_account_from_dict(creds)
    else:
        # PERHATIAN: Jika SERVICE_ACCOUNT_JSON kosong, ini akan mencari file lokal
        # Pastikan file 'service-account-key.json' ada di direktori yang sama.
        # NOTE: Jika koneksi gagal di sini, variabel worksheet akan tetap None
        gc = gspread.service_account(filename='service-account-key.json')
    
    sh = gc.open(SHEET_TITLE)
    worksheet_expense = sh.worksheet(WORKSHEET_EXPENSE)
    worksheet_income = sh.worksheet(WORKSHEET_INCOME) # Inisialisasi Worksheet Pemasukan

except Exception as e:
    # Mengatasi 'Gagal terhubung ke Google Sheets'
    print(f"ERROR: Gagal terhubung ke Google Sheets: {e}")
    worksheet_expense = None
    worksheet_income = None


# --- FUNGSI UTILITY ---

def safe_to_date(series):
    """Mengkonversi kolom Pandas/Numpy datetime64 menjadi objek datetime Python standar."""
    # Mengubah datetime64/Timestamp ke datetime.date Python biasa
    # Tambahkan .date() untuk memastikan ini adalah tipe Python date, bukan datetime yang kompleks.
    return series.apply(lambda x: x.to_pydatetime().date() if pd.notnull(x) else None)

def get_data_dataframe(worksheet):
    """Mengambil data dari Worksheet spesifik, membersihkan, dan mengembalikannya sebagai Pandas DataFrame."""
    if not worksheet:
        return pd.DataFrame()
    try:
        data = worksheet.get_all_values()
        
        if not data or len(data) <= 1:
            # Mengembalikan DataFrame kosong dengan headers yang benar
            if worksheet.title == WORKSHEET_INCOME:
                 return pd.DataFrame(columns=['Tanggal', 'Modal', 'Jual', 'Via', 'Catatan'])
            else:
                 return pd.DataFrame(columns=['Tanggal', 'Metode', 'Nominal', 'Catatan'])

        headers = data[0]
        rows = data[1:]
        
        df = pd.DataFrame(rows, columns=headers)
        
        # 1. Konversi Tanggal
        # errors='coerce' akan mengubah tanggal yang tidak valid menjadi NaT (Not a Time)
        df['Tanggal'] = pd.to_datetime(df['Tanggal'], errors='coerce')
        # Menghapus baris yang Tanggal-nya tidak valid 
        df.dropna(subset=['Tanggal'], inplace=True)
        
        # 2. Perlakuan khusus untuk Pemasukan (menghitung Profit)
        if worksheet.title == WORKSHEET_INCOME:
            # Konversi numerik dan pastikan tipenya int standar Python
            df['Modal'] = pd.to_numeric(df['Modal'], errors='coerce').fillna(0).astype(int)
            df['Jual'] = pd.to_numeric(df['Jual'], errors='coerce').fillna(0).astype(int)
            
            # Hitung Profit, pastikan hasilnya int standar Python
            df['Profit'] = (df['Jual'] - df['Modal']).astype(int) 
            
            # Field 'Nominal' di-override agar total/chart utility bisa menggunakannya
            df['Nominal'] = df['Profit'] # Sudah bertipe int
            
        else:
            # Perlakuan untuk Pengeluaran
            # Konversi numerik dan pastikan tipenya int standar Python
            df['Nominal'] = pd.to_numeric(df['Nominal'], errors='coerce').fillna(0).astype(int)

        # Menambahkan indeks baris Sheets (row index 2 adalah baris data pertama)
        df['row_index'] = range(2, len(df) + 2)
        
        # Urutkan berdasarkan tanggal (menghindari 'settingwithcopywarning')
        df_sorted = df.sort_values(by='Tanggal', ascending=False).copy()

        return df_sorted
    
    except Exception as e:
        print(f"ERROR saat mengambil data dari Sheets ({worksheet.title}): {e}")
        return pd.DataFrame()

def calculate_charts(df):
    """Menghitung data untuk chart mingguan dan bulanan berdasarkan kolom 'Nominal' (bisa Nominal atau Profit)."""
    if df.empty:
        # Mengembalikan list kosong untuk menghindari error chart.js
        return [], [], [], []

    # Semua logika chart tetap sama
    
    # --- Chart Mingguan ---
    today = datetime.now().date()
    # Pastikan df['Tanggal'] di-coerce ke datetime.date Python untuk perbandingan
    df['date_only'] = safe_to_date(df['Tanggal']) 
    start_of_week = today - timedelta(days=today.weekday())
    
    weekly_data = df[df['date_only'] >= start_of_week].copy()
    # Menggunakan dt.dayofweek untuk memastikan urutan hari yang benar
    weekly_summary = weekly_data.groupby(weekly_data['Tanggal'].dt.dayofweek)['Nominal'].sum()
    
    # Mapping angka hari ke nama hari (0=Senin, 6=Minggu)
    day_map = {0: 'Sen', 1: 'Sel', 2: 'Rab', 3: 'Kam', 4: 'Jum', 5: 'Sab', 6: 'Min'}
    # Reindex untuk memastikan 7 hari selalu ada. Pastikan fill_value juga int
    full_week_summary = weekly_summary.reindex(range(7), fill_value=0)
    
    weekly_labels = [day_map[i] for i in full_week_summary.index.tolist()]
    # Konversi ke list Python standar
    weekly_data_values = [int(val) for val in full_week_summary.values.tolist()]

    # --- Chart Bulanan ---
    df['BulanTahun'] = df['Tanggal'].dt.to_period('M')
    monthly_summary = df.groupby('BulanTahun')['Nominal'].sum().sort_index()
    
    monthly_labels = [period.strftime('%b %y') for period in monthly_summary.index]
    # Konversi ke list Python standar untuk JSON serializable
    monthly_data_values = [int(val) for val in monthly_summary.values.tolist()]
    
    return weekly_labels, weekly_data_values, monthly_labels, monthly_data_values

def calculate_totals(df):
    """Menghitung total harian dan mingguan berdasarkan kolom 'Nominal' (Pengeluaran atau Profit)."""
    if df.empty:
        return 0, 0

    today = datetime.now().date()
    # Pastikan df['Tanggal'] di-coerce ke datetime.date Python untuk perbandingan
    df['date_only'] = safe_to_date(df['Tanggal']) 
    start_of_week = today - timedelta(days=today.weekday())
    
    # Total Harian
    df_today = df[df['date_only'] == today]
    # FIX: Pastikan hasil sum diubah menjadi int Python standar
    total_harian = int(df_today['Nominal'].sum())

    # Total Mingguan 
    df_week = df[df['date_only'] >= start_of_week]
    # FIX: Pastikan hasil sum diubah menjadi int Python standar
    total_mingguan = int(df_week['Nominal'].sum())
    
    return total_harian, total_mingguan


# --- RUTE FLASK UTAMA ---

@app.route('/', methods=['GET', 'POST'])
@app.route('/pengeluaran', methods=['GET', 'POST'])
def pengeluaran_index():
    df = get_data_dataframe(worksheet_expense)
    
    if request.method == 'POST':
        # Logika POST Pengeluaran... (tidak ada perubahan pada bagian ini)
        tanggal_str = request.form.get('tanggal')
        metode = request.form.get('metode')
        nominal_str = request.form.get('nominal')
        catatan = request.form.get('catatan', '')
        
        # Validasi Input Dasar
        if not (tanggal_str and metode and nominal_str):
             flash('⚠️ Semua field wajib (Tanggal, Nominal, Metode) harus diisi.', 'warning')
             return redirect(url_for('pengeluaran_index'))

        try:
            nominal = int(nominal_str)
        except ValueError:
            flash('🚨 Nominal harus berupa angka.', 'danger')
            return redirect(url_for('pengeluaran_index'))

        # Validasi Batas Nominal (1000 - 200000)
        if not (1000 <= nominal <= 200000):
            flash('🚨 Nominal harus antara Rp 1.000 hingga Rp 200.000.', 'danger')
            return redirect(url_for('pengeluaran_index'))
            
        # Validasi Batas Tanggal (Mundur 2 hari, Maju 1 hari)
        try:
            tanggal_input = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            batas_bawah = today - timedelta(days=2)
            batas_atas = today + timedelta(days=1)
            if not (batas_bawah <= tanggal_input <= batas_atas):
                flash('🚨 Tanggal harus berada dalam rentang H-2 sampai H+1.', 'danger')
                return redirect(url_for('pengeluaran_index'))
        except ValueError:
            flash('🚨 Format tanggal tidak valid.', 'danger')
            return redirect(url_for('pengeluaran_index'))
            
        # Menyimpan Data ke Google Sheets
        if worksheet_expense:
            try:
                # Kolom default (Tanggal, Metode, Nominal, Catatan)
                data_row = [tanggal_str, metode.lower(), nominal, catatan] 
                worksheet_expense.append_row(data_row)
                flash('✅ Pengeluaran berhasil dicatat!', 'success')
            except Exception as e:
                flash(f'❌ Gagal menyimpan data Pengeluaran. Error: {e}', 'danger')
        else:
             flash('❌ Gagal menyimpan data: Koneksi ke Google Sheets tidak tersedia.', 'danger')
        
        return redirect(url_for('pengeluaran_index'))

    # --- Bagian GET Request ---
    
    # Hitung data untuk chart dan total
    weekly_labels, weekly_data, monthly_labels, monthly_data = calculate_charts(df)
    total_harian, total_mingguan = calculate_totals(df)

    # Konversi DataFrame ke format Python standar (dict)
    pengeluaran_list_raw = df.head(10).to_dict('records')
    pengeluaran_list = []
    for item in pengeluaran_list_raw:
        # FIX: Mengkonversi objek Timestamp Pandas ke string yang bisa diproses di Jinja2
        if item.get('Tanggal') and pd.notnull(item['Tanggal']):
            # Pastikan ini adalah objek Timestamp sebelum memanggil strftime
            if isinstance(item['Tanggal'], pd.Timestamp):
                 item['Tanggal'] = item['Tanggal'].strftime('%Y-%m-%d')
            # Jika sudah string atau type lain, biarkan saja (walaupun seharusnya sudah di-handle di get_data_dataframe)
        
        # FIX: Pastikan Nominal diubah ke int Python standar
        if item.get('Nominal') is not None:
             item['Nominal'] = int(item['Nominal'])

        pengeluaran_list.append(item)


    current_date = datetime.now().strftime('%Y-%m-%d')
    batas_atas_str = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
    batas_bawah_str = (datetime.now().date() - timedelta(days=2)).strftime('%Y-%m-%d')

    return render_template('index.html', 
                            tab_active='pengeluaran', # Untuk mengaktifkan tab yang benar
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
                            # FIX: Tambahkan variabel untuk Pemasukan/Profit, set ke 0
                            total_harian_profit=0,
                            total_mingguan_profit=0,
                            chart_labels_mingguan_inc=[],
                            chart_data_mingguan_inc=[],
                            chart_labels_bulanan_inc=[],
                            chart_data_bulanan_inc=[],
                            batas_nominal_min_inc=10000 
                            )


@app.route('/pemasukan', methods=['GET', 'POST'])
def pemasukan_index():
    df = get_data_dataframe(worksheet_income) # Ambil data Pemasukan
    
    if request.method == 'POST':
        # Logika POST Pemasukan... (tidak ada perubahan pada bagian ini)
        tanggal_str = request.form.get('tanggal')
        modal_str = request.form.get('modal')
        jual_str = request.form.get('jual')
        via = request.form.get('via')
        catatan = request.form.get('catatan', '')

        # Validasi Input Dasar Pemasukan
        if not (tanggal_str and modal_str and jual_str and via):
             flash('⚠️ Semua field wajib (Tanggal, Modal, Jual, Via) harus diisi.', 'warning')
             return redirect(url_for('pemasukan_index'))

        try:
            modal = int(modal_str)
            jual = int(jual_str)
        except ValueError:
            flash('🚨 Nominal Modal dan Jual harus berupa angka.', 'danger')
            return redirect(url_for('pemasukan_index'))

        # Validasi Batas Nominal (minimal 10000)
        if not (modal >= 10000 and jual >= 10000):
            flash('🚨 Nominal Modal dan Jual minimal harus Rp 10.000.', 'danger')
            return redirect(url_for('pemasukan_index'))
            
        # Validasi Batas Tanggal (Mundur 2 hari, Maju 1 hari)
        try:
            tanggal_input = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            batas_bawah = today - timedelta(days=2)
            batas_atas = today + timedelta(days=1)
            if not (batas_bawah <= tanggal_input <= batas_atas):
                flash('🚨 Tanggal harus berada dalam rentang H-2 sampai H+1.', 'danger')
                return redirect(url_for('pemasukan_index'))
        except ValueError:
            flash('🚨 Format tanggal tidak valid.', 'danger')
            return redirect(url_for('pemasukan_index'))
            
        # Menyimpan Data ke Google Sheets
        if worksheet_income:
            try:
                data_row = [
                    tanggal_str,
                    modal,
                    jual,
                    via.lower(),
                    catatan
                ]
                worksheet_income.append_row(data_row)
                flash('✅ Pemasukan berhasil dicatat!', 'success')
            except Exception as e:
                flash(f'❌ Gagal menyimpan data Pemasukan. Error: {e}', 'danger')
        else:
             flash('❌ Gagal menyimpan data: Koneksi ke Google Sheets tidak tersedia.', 'danger')
        
        return redirect(url_for('pemasukan_index'))

    # --- Bagian GET Request ---
    
    # Hitung data untuk chart dan total (berdasarkan Profit)
    weekly_labels, weekly_data, monthly_labels, monthly_data = calculate_charts(df)
    total_harian_profit, total_mingguan_profit = calculate_totals(df)

    # Konversi DataFrame ke format Python standar (dict)
    pemasukan_list_raw = df.head(10).to_dict('records')
    pemasukan_list = []
    for item in pemasukan_list_raw:
        # FIX: Mengkonversi objek Timestamp Pandas ke string yang bisa diproses di Jinja2
        if item.get('Tanggal') and pd.notnull(item['Tanggal']):
            # Pastikan ini adalah objek Timestamp sebelum memanggil strftime
            if isinstance(item['Tanggal'], pd.Timestamp):
                 item['Tanggal'] = item['Tanggal'].strftime('%Y-%m-%d')
        
        # FIX: Pastikan Nominal dan Profit diubah ke int Python standar
        if item.get('Modal') is not None:
            item['Modal'] = int(item['Modal'])
        if item.get('Jual') is not None:
            item['Jual'] = int(item['Jual'])
        if item.get('Profit') is not None:
             item['Profit'] = int(item['Profit'])

        pemasukan_list.append(item)


    current_date = datetime.now().strftime('%Y-%m-%d')
    batas_atas_str = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
    batas_bawah_str = (datetime.now().date() - timedelta(days=2)).strftime('%Y-%m-%d')

    return render_template('index.html', 
                            tab_active='pemasukan', # Untuk mengaktifkan tab yang benar
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
                            # FIX: Tambahkan variabel untuk Pengeluaran, set ke 0
                            total_harian=0,
                            total_mingguan=0,
                            chart_labels_mingguan=[],
                            chart_data_mingguan=[],
                            chart_labels_bulanan=[],
                            chart_data_bulanan=[],
                            batas_nominal_max=200000,
                            batas_nominal_min=1000
                            )


@app.route('/delete', methods=['POST'])
def delete_entry():
    """Rute untuk menghapus baris data berdasarkan row_index dan jenis tab."""
    row_index_str = request.form.get('row_index')
    tab_type = request.form.get('tab_type') # Mengetahui dari tab mana delete dipicu

    worksheet_to_use = None
    if tab_type == 'pengeluaran':
        worksheet_to_use = worksheet_expense
        log_name = "Pengeluaran"
        redirect_route = 'pengeluaran_index'
    elif tab_type == 'pemasukan':
        worksheet_to_use = worksheet_income
        log_name = "Pemasukan"
        redirect_route = 'pemasukan_index'
    else:
        flash('❌ Kesalahan internal: Jenis tab tidak dikenal.', 'danger')
        return redirect(url_for('pengeluaran_index'))


    if not worksheet_to_use or not row_index_str:
        flash(f'❌ Gagal menghapus data {log_name}: Koneksi Sheets atau indeks tidak ditemukan.', 'danger')
        return redirect(url_for(redirect_route)) 
    
    try:
        row_index = int(row_index_str)
        
        if row_index < 2:
            flash('🚨 Indeks baris tidak valid untuk dihapus.', 'warning')
            return redirect(url_for(redirect_route)) 
        
        worksheet_to_use.delete_rows(row_index)
        flash(f'🗑️ Data {log_name} berhasil dihapus.', 'info')
        
    except Exception as e:
        flash(f'❌ Terjadi kesalahan saat menghapus data: {e}', 'danger')
        print(f"Delete Error: {e}")

    # Redirect kembali ke tab yang sama
    return redirect(url_for(redirect_route))


if __name__ == '__main__':
    # Pastikan debug=True hanya saat development
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
