import os
import pandas as pd
import streamlit as st

# Absolute path agar aman dipanggil dari direktori manapun
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "data", "database_scheduler.xlsx")


@st.cache_data
def load_database():
    """Membaca seluruh sheet dari file Excel master dan menyimpannya ke cache Streamlit."""
    if not os.path.exists(DATABASE):
        st.error(f"❌ File database tidak ditemukan di lokasi:\n{DATABASE}")
        st.stop()

    try:
        excel = pd.ExcelFile(DATABASE, engine="openpyxl")
        data = {}

        for sheet in excel.sheet_names:
            clean_sheet_name = str(sheet).strip()
            data[clean_sheet_name] = pd.read_excel(
                DATABASE, sheet_name=sheet, engine="openpyxl"
            )

        return data

    except Exception as e:
        st.error(
            "❌ Gagal membaca file Excel. Pastikan file tidak sedang dibuka di Excel/WPS."
        )
        st.error(str(e))
        st.stop()


# ==========================================================
# Fungsi-fungsi Pembantu (Disesuaikan dengan Nama Sheet Anda)
# ==========================================================


def get_guru():
    return load_database().get("Guru", pd.DataFrame())


def get_mapel():
    return load_database().get("Mapel", pd.DataFrame())


def get_rombel():
    return load_database().get("Rombel", pd.DataFrame())


def get_mengajar():
    return load_database().get("Mengajar", pd.DataFrame())


def get_slot():
    return load_database().get("Slot", pd.DataFrame())
