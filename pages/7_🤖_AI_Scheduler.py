import streamlit as st
from database import DatabaseManager
from scheduler_core.constraints import ConstraintManager
from scheduler_core.solver import SchedulerSolver
from scheduler_core.exporter import ScheduleExporter

st.set_page_config(page_title="AI Scheduler", page_icon="🤖", layout="wide")

st.title("🤖 AI Scheduler Engine")
st.write("Jalankan algoritma optimasi AI untuk menyusun jadwal pelajaran secara otomatis.")

db = DatabaseManager()
data = db.load_all_data()

days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]
max_hours = 9

if st.button("🚀 Generasi Jadwal Otomatis", type="primary"):
    with st.spinner("AI sedang mengoptimasi jadwal... Mohon tunggu..."):
        constraint_mgr = ConstraintManager(data)
        assignments = constraint_mgr.get_lesson_splits()
        mgmp_days = constraint_mgr.get_teacher_mgmp_days()

        solver = SchedulerSolver(assignments, days=days, max_hours_per_day=max_hours)
        results_df = solver.solve(mgmp_constraints=mgmp_days)

        if results_df is not None and not results_df.empty:
            st.success("🎉 Jadwal berhasil dibuat tanpa bentrok!")
            
            st.subheader("📌 Matriks Jadwal Pelajaran")
            matrix = ScheduleExporter.format_timetable(results_df)
            st.dataframe(matrix, use_container_width=True)

            # Download Option
            excel_file = ScheduleExporter.export_to_excel(results_df)
            with open(excel_file, "rb") as f:
                st.download_button(
                    label="📥 Download Jadwal Excel",
                    data=f,
                    file_name="Jadwal_Pelajaran_Hasil_AI.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error("❌ Solusi tidak ditemukan! Periksa kembali batasan constraint atau total jam mengajar.")
