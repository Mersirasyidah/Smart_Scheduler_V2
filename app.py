import io
import pandas as pd
import streamlit as st
from solver import SchedulerSolver

st.set_page_config(page_title="AI Scheduler", page_icon="🤖", layout="wide")

st.title("🤖 AI Scheduler - Generator Jadwal Otomatis")
st.caption("Optimasi pembuatan jadwal KBM menggunakan CP-SAT Constraint Programming Solver")

# 1. INISIALISASI SESSION STATE DATA
if "scheduler_data" not in st.session_state:
    st.session_state["scheduler_data"] = None


class SchedulerData:
    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df


# 2. SIDEBAR UPLOAD & INTEGRASI SESSION STATE
st.sidebar.header("📁 Data Master")
uploaded_file = st.sidebar.file_uploader("Upload File Excel Master", type=["xlsx", "xls"])

if uploaded_file:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        
        # Mencegah error beda nama sheet (Mengajar vs Guru_Mengajar, Slot vs Hari_Jam)
        sheets = excel_file.sheet_names
        
        sheet_mengajar = "Mengajar" if "Mengajar" in sheets else "Guru_Mengajar"
        sheet_slot = "Slot" if "Slot" in sheets else "Hari_Jam"

        guru_df = pd.read_excel(excel_file, "Guru")
        rombel_df = pd.read_excel(excel_file, "Rombel")
        mengajar_df = pd.read_excel(excel_file, sheet_mengajar)
        mapel_df = pd.read_excel(excel_file, "Mapel")
        slot_df = pd.read_excel(excel_file, sheet_slot)

        # Simpan ke Session State!
        st.session_state["scheduler_data"] = SchedulerData(
            guru_df, rombel_df, mengajar_df, mapel_df, slot_df
        )
        st.sidebar.success("✅ Data Master Siap!")

    except Exception as e:
        st.sidebar.error(f"❌ Gagal membaca file: {e}")

# 3. PENGECEKAN DATA MASTER (GUARD CLAUSE)
if st.session_state["scheduler_data"] is None:
    st.warning("⚠️ **Data Master Belum Siap!**")
    st.info("Silakan unggah file Excel data master di sidebar kiri terlebih dahulu untuk mulai me-generate jadwal.")
    st.stop() # Hentikan eksekusi script di bawahnya jika data belum ada

# ==========================================================
# 4. KODE EKSEKUSI SOLVER (BERJALAN JIKA DATA SUDAH SIAP)
# ==========================================================
scheduler_data = st.session_state["scheduler_data"]

st.success("🎉 Data Master Terdeteksi & Siap Digunakan!")
if st.button("🚀 Process Penjadwalan Otomatis", type="primary"):
    # ... (Proses running solver sama seperti kode sebelumnya)
    pass
