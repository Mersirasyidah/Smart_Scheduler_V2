import streamlit as st
import pandas as pd
from database import DatabaseManager
from scheduler_core.solver import SchedulerSolver
from scheduler_core.exporter import ScheduleExporter

st.set_page_config(page_title="AI Scheduler", page_icon="🤖", layout="wide")

st.title("🤖 AI Scheduler Engine")
st.write("Jalankan algoritma optimasi AI untuk menyusun jadwal pelajaran secara otomatis.")

# 1. Load Data dari DatabaseManager
class SchedulerDataContainer:
    """Wrapper untuk menyediakan atribut yang dibutuhkan oleh SchedulerSolver."""
    def __init__ (self):
        db = DatabaseManager()
        data = db.load_all_data()
        self.guru = data["guru"]
        self.rombel = data["rombel"]
        self.mengajar = data["guru_mengajar"]
        self.mapel = data["mapel"]
        self.slot = data["hari_jam"]

# Pilihan Parameter di UI
timeout = st.slider("Waktu Maksimal Optimasi (detik)", min_value=10, max_value=300, value=60, step=10)

if st.button("🚀 Generasi Jadwal Otomatis", type="primary"):
    with st.spinner("AI sedang mengoptimasi jadwal... Mohon tunggu..."):
        # 2. Bungkus Data ke Container
        scheduler_data = SchedulerDataContainer()

        # 3. Inisialisasi dan Jalankan Solver
        solver = SchedulerSolver(scheduler_data)
        is_success = solver.run_solver(timeout_seconds=timeout)

        if is_success:
            st.success("🎉 Jadwal berhasil dibuat tanpa bentrok!")
            
            # 4. Ekstrak Hasil
            df_results = solver.extract_results()
            
            st.subheader("📋 Detail Hasil Penjadwalan")
            st.dataframe(df_results, use_container_width=True)

            # 5. Format & Download
            excel_file = ScheduleExporter.export_to_excel(df_results)
            with open(excel_file, "rb") as f:
                st.download_button(
                    label="📥 Download Jadwal Excel",
                    data=f,
                    file_name="Jadwal_Pelajaran_Hasil_AI.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error("❌ Solusi tidak ditemukan! Periksa kembali batasan constraint atau total jam mengajar.")
