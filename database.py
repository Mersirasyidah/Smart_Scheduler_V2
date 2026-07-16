# database.py
import os
import pandas as pd
import streamlit as st

# Lokasi file database Excel di dalam folder data
DATABASE = "data/database_scheduler.xlsx"


def load_database():
    """
    Membaca seluruh sheet dari file Excel
    Mengembalikan dictionary:
    {
        "Guru": dataframe,
        "Mapel": dataframe,
        ...
    }
    """
    # Cek apakah file ada
    if not os.path.exists(DATABASE):
        st.error(f"❌ File database tidak ditemukan di lokasi:\n{DATABASE}")
        st.stop()

    try:
        # Membaca seluruh workbook
        excel = pd.ExcelFile(DATABASE, engine="openpyxl")
        data = {}

        for sheet in excel.sheet_names:
            data[sheet] = pd.read_excel(
                DATABASE,
                sheet_name=sheet,
                engine="openpyxl"
            )

        return data

    except Exception as e:
        st.error("❌ Gagal membaca file Excel. Pastikan file tidak sedang dibuka di Excel/WPS.")
        st.error(str(e))
        st.stop()


# ==========================================================
# Fungsi-fungsi pembantu (Sesuai nama sheet asli Excel Anda)
# ==========================================================

def get_guru():
    return load_database().get("Guru", pd.DataFrame())


def get_mapel():
    return load_database().get("Mapel", pd.DataFrame())


def get_rombel():
    return load_database().get("Rombel", pd.DataFrame())


def get_mengajar():
    return load_database().get("Guru_Mengajar", pd.DataFrame())


def get_hari_jam():
    return load_database().get("Hari_Jam", pd.DataFrame())


if __name__ == "__main__":
    print("=" * 50)
    print("SMART SCHEDULER V2 - DATABASE CHECK")
    print("=" * 50)
    print("Folder kerja    :", os.getcwd())
    print("Lokasi database :", DATABASE)
    print("File ditemukan  :", os.path.exists(DATABASE))
