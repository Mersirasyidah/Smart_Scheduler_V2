import pandas as pd

# GANTI NAMA FILE INI DENGAN NAMA FILE EXCEL ANDA
nama_file_excel = "Data_Jadwal.xlsx"

try:
    excel_file = pd.ExcelFile(nama_file_excel)
    print("=== SHEET YANG DITEMUKAN DALAM EXCEL ===")
    print(excel_file.sheet_names)
    print("\n" + "=" * 40 + "\n")

    for sheet in excel_file.sheet_names:
        df = pd.read_excel(nama_file_excel, sheet_name=sheet)
        print(f"📄 Sheet: '{sheet}' (Jumlah Baris: {len(df)})")
        print("   Nama Kolom:", list(df.columns))
        print("   3 Baris Pertama Data:")
        print(df.head(3))
        print("-" * 50)
except Exception as e:
    print(f"❌ Gagal membaca file: {e}")
