# app.py atau pages/1_AI_Scheduler.py
import io
import os
import sys
import pandas as pd
import streamlit as st

# ==========================================
# 1. PERBAIKAN IMPORT PATH & MODUL OOP
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from scheduler_core.exporter import ScheduleExporter
    from scheduler_core.solver import SchedulerSolver
except ImportError as e:
    # Fallback jika struktur folder sejajar tanpa folder 'pages'
    try:
        from scheduler_core.exporter import ScheduleExporter
        from scheduler_core.solver import SchedulerSolver
    except ImportError:
        st.error(
            f"❌ **Gagal Mengimpor Core Engine**: {e}\n\n"
            "Pastikan folder `scheduler_core/` berisi `solver.py`, `constraints.py`, dan `exporter.py`."
        )
        st.stop()

# ==========================================
# 2. KONFIGURASI HALAMAN STREAMLIT
# ==========================================
st.set_page_config(
    page_title="AI Scheduler Engine", page_icon="🤖", layout="wide"
)

st.title("🤖 AI Scheduler - Generator Jadwal Otomatis")
st.caption(
    "Optimasi pembuatan jadwal KBM menggunakan CP-SAT Constraint Programming Solver"
)
st.markdown("---")

# ==========================================
# 3. VERIFIKASI DATA DI SESSION STATE
# ==========================================
if "scheduler" not in st.session_state:
    st.warning(
        "⚠️ **Data Master Belum Siap!**\n\n"
        "Silakan unggah dan siapkan data master (Guru, Rombel, Mengajar, Mapel, Slot) di menu awal sebelum menjalankan AI Generator."
    )
    st.stop()

scheduler_data = st.session_state["scheduler"]

# ==========================================
# 4. SIDEBAR - PANEL KONTROL SOLVER
# ==========================================
st.sidebar.header("⚙️ Pengaturan Solver")
timeout_sec = st.sidebar.slider(
    "Timeout Solver (Detik)",
    min_value=30,
    max_value=300,
    value=90,
    step=30,
)
max_jam_nongtt = st.sidebar.slider(
    "Batas Max Jam MGMP Non-GTT",
    min_value=1,
    max_value=6,
    value=3,
    help="Batas maksimum jam mengajar guru Non-GTT pada hari MGMP sebelum dikenakan penalti soft-constraint.",
)

st.markdown("### 📋 Status Data Master")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

# Ambil data frame dari scheduler_data baik berbentuk Dict maupun DataLoader
guru_df = (
    scheduler_data.get("Guru")
    if isinstance(scheduler_data, dict)
    else getattr(scheduler_data, "guru", pd.DataFrame())
)
rombel_df = (
    scheduler_data.get("Rombel")
    if isinstance(scheduler_data, dict)
    else getattr(scheduler_data, "rombel", pd.DataFrame())
)
mapel_df = (
    scheduler_data.get("Mapel")
    if isinstance(scheduler_data, dict)
    else getattr(scheduler_data, "mapel", pd.DataFrame())
)
mengajar_df = (
    scheduler_data.get("Mengajar")
    if isinstance(scheduler_data, dict)
    else getattr(scheduler_data, "mengajar", pd.DataFrame())
)

with col_s1:
    st.metric("Total Guru", len(guru_df) if not guru_df.empty else "N/A")
with col_s2:
    st.metric("Total Rombel", len(rombel_df) if not rombel_df.empty else "N/A")
with col_s3:
    st.metric("Total Mapel", len(mapel_df) if not mapel_df.empty else "N/A")
with col_s4:
    st.metric(
        "Tugas Mengajar", len(mengajar_df) if not mengajar_df.empty else "N/A"
    )

st.markdown("---")

# ==========================================
# 5. TOMBOL EKSEKUSI GENERATE JADWAL
# ==========================================
if st.button("🚀 Generate Jadwal Sekarang", type="primary", use_container_width=True):
    with st.spinner("🔍 Menjalankan CP-SAT Optimization Solver..."):
        solver = SchedulerSolver(scheduler_data)
        success = solver.run_solver(
            timeout_seconds=timeout_sec, max_jam_mgmp_nongtt=max_jam_nongtt
        )

        if success:
            df_jadwal = solver.extract_results()
            st.session_state["df_jadwal_hasil"] = df_jadwal
            st.success("🎉 **Penjadwalan Berhasil Dibuat Tanpa Bentrok!**")
        else:
            st.session_state.pop("df_jadwal_hasil", None)
            st.error(
                "❌ **Solver Gagal Menemukan Solusi!**\n\n"
                "**Saran Perbaikan:**\n"
                "1. Periksa ketersediaan jam mengajar guru (bentrok ketersediaan).\n"
                "2. Cek apakah total JP kelas melebihi total jam slot pembelajaran yang tersedia.\n"
                "3. Longgarkan **Batas Max Jam MGMP Non-GTT** pada sidebar."
            )

# ==========================================
# 6. TAMPILAN HASIL & EKSPOR DATA
# ==========================================
if (
    "df_jadwal_hasil" in st.session_state
    and not st.session_state["df_jadwal_hasil"].empty
):
    df_jadwal = st.session_state["df_jadwal_hasil"]

    tab1, tab2 = st.tabs(["📅 Jadwal Master", "📥 Export Hasil (Excel)"])

    with tab1:
        st.subheader("📌 Matriks Jadwal Pelajaran Utama")

        # Filter Rombel
        list_rombel = sorted(df_jadwal["ID_Rombel"].unique().tolist())
        selected_rombel = st.selectbox(
            "Pilih Rombel / Kelas:", ["Semua Rombel"] + list_rombel
        )

        if selected_rombel != "Semua Rombel":
            df_view = df_jadwal[df_jadwal["ID_Rombel"] == selected_rombel]
        else:
            df_view = df_jadwal

        st.dataframe(df_view, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("📥 Unduh Laporan Excel / CSV Terformat")
        st.write(
            "Mengunduh file Excel lengkap yang berisi **Sheet Vertikal Master** dan **Sheet Pivot Matriks per Kelas**."
        )

        # Menggunakan ScheduleExporter OOP untuk ekspor serbaguna
        exporter = ScheduleExporter(df_jadwal, scheduler_data)
        excel_bytes = exporter.generate_excel()

        st.download_button(
            label="📦 Download File Excel (.xlsx)",
            data=excel_bytes,
            file_name="Jadwal_KBM_Sekolah.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
