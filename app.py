import os
import pandas as pd
import streamlit as st
from solver import SchedulerSolver

# ==========================================================
# 1. FUNGSIONALITAS PEMBACAAN DATA LANGSUNG (AUTO-LOAD)
# ==========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATABASE_PATH = os.path.join(BASE_DIR, "data", "database_scheduler.xlsx")

class SchedulerData:
    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df

def load_master_data(uploaded_file=None):
    """Membaca data master baik dari upload manual maupun file lokal bawaan."""
    try:
        if uploaded_file is not None:
            excel_file = pd.ExcelFile(uploaded_file)
        elif os.path.exists(DEFAULT_DATABASE_PATH):
            excel_file = pd.ExcelFile(DEFAULT_DATABASE_PATH)
        else:
            return None

        sheets = [s.strip() for s in excel_file.sheet_names]
        
        # Pembacaan sheet dengan toleransi nama
        guru_df = pd.read_excel(excel_file, "Guru")
        rombel_df = pd.read_excel(excel_file, "Rombel" if "Rombel" in sheets else "Kelas")
        mengajar_df = pd.read_excel(excel_file, "Mengajar" if "Mengajar" in sheets else "Guru_Mengajar")
        mapel_df = pd.read_excel(excel_file, "Mapel")
        slot_df = pd.read_excel(excel_file, "Slot" if "Slot" in sheets else "Hari_Jam")

        return SchedulerData(guru_df, rombel_df, mengajar_df, mapel_df, slot_df)
    except Exception as e:
        st.error(f"Error membaca sheet Excel: {e}")
        return None

# ==========================================================
# 2. INISIALISASI STREAMLIT & SIDEBAR
# ==========================================================
st.sidebar.header("📁 Unggah Data Excel Master")
uploaded_file = st.sidebar.file_uploader("Upload File Excel (Opsional)", type=["xlsx", "xls"])

# Coba muat data dari Upload -> Jika tidak ada, muat dari Database Lokal
scheduler_data = load_master_data(uploaded_file)

timeout_user = st.sidebar.slider("Total Durasi Timeout Solver (Detik)", 30, 300, 120, 30)

# ==========================================================
# 3. PENGECEKAN DATA (GUARD CLAUSE)
# ==========================================================
if scheduler_data is None:
    st.error("⚠️ **Data Master Belum Siap!**")
    st.info(
        f"Sistem tidak menemukan file database otomatis di: `{DEFAULT_DATABASE_PATH}`.\n\n"
        "**Solusi:** Silakan unggah file Excel Master (yang berisi sheet Guru, Rombel, Mengajar, Mapel, Slot) "
        "melalui tombol **'Upload File Excel'** di sidebar sebelah kiri."
    )
    st.stop()
