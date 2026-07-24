import os
import pandas as pd
import streamlit as st

# Menggunakan absolute path agar aman dijalankan dari direktori manapun
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "data", "database_scheduler.xlsx")


# Gunakan cache_data agar Excel tidak dibaca ulang terus-menerus
@st.cache_data
def load_database():
    """
    Membaca seluruh sheet dari file Excel dan menyimpannya ke cache.
    """
    if not os.path.exists(DATABASE):
        st.error(f"❌ File database tidak ditemukan di lokasi:\n{DATABASE}")
        st.stop()

    try:
        excel = pd.ExcelFile(DATABASE, engine="openpyxl")
        data = {}

        for sheet in excel.sheet_names:
            # Strip untuk mengantisipasi spasi tersembunyi pada nama sheet
            clean_sheet_name = str(sheet).strip()
            data[clean_sheet_name] = pd.read_excel(
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
# Fungsi-fungsi pembantu dengan pembersihan cache opsional
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
    print("File ditemukan :", os.path.exists(DATABASE))
