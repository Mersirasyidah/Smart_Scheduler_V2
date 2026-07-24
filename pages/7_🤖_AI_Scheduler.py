import io
import os
import sys
import pandas as pd
import streamlit as st

# ==========================================
# 1. PERBAIKAN IMPORT PATH (SYSTEM PATH RESOLVER)
# ==========================================
# Menambahkan root directory ke sys.path agar file di folder pages/
# dapat mengimpor modul dari folder utama maupun subfolder (scheduler_core)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Import engine solver & exporter
try:
    from scheduler_engine import (
        SchedulerSolver,
        execute_scheduler_with_fallback,
    )
    from scheduler_core.exporter import ScheduleExporter
except ImportError as e:
    st.error(
        f"❌ **Gagal Mengimpor Modul System**: {e}\n\n"
        "Pastikan file `scheduler_engine.py` dan folder `scheduler_core/` berada di root direktori project Anda."
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
# 3. VERIFIKASI DATA MASTER DI SESSION STATE
# ==========================================
if "scheduler" not in st.session_state:
    st.warning(
        "⚠️ **Data Master Belum Diunggah / Siap!**\n\n"
        "Silakan siapkan data master (Guru, Rombel, Mengajar, Mapel, Slot) di menu awal sebelum menggunakan AI Generator ini."
    )
    st.stop()

scheduler_data = st.session_state["scheduler"]

# ==========================================
# 4. SIDEBAR - PANEL KONTROL SOLVER
# ==========================================
st.sidebar.header("⚙️ Pengaturan Solver")
timeout_sec = st.sidebar.slider(
    "Timeout Max per Skenario (Detik)",
    min_value=30,
    max_value=300,
    value=90,
    step=30,
)
max_jp_daily = st.sidebar.number_input(
    "Batas Max JP Guru / Hari", min_value=4, max_value=10, value=6
)
use_fallback = st.sidebar.checkbox(
    "Gunakan Multi-Skenario Fallback",
    value=True,
    help="Jika diaktifkan, solver akan melonggarkan batasan secara bertahap jika skenario awal gagal.",
)

# Panel Informasi Data Master
st.markdown("### 📋 Status Data Master Terdeteksi")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

with col_s1:
    st.metric(
        "Total Guru",
        (
            len(scheduler_data.guru)
            if hasattr(scheduler_data, "guru")
            else "N/A"
        ),
    )
with col_s2:
    st.metric(
        "Total Rombel",
        (
            len(scheduler_data.rombel)
            if hasattr(scheduler_data, "rombel")
            else "N/A"
        ),
    )
with col_s3:
    st.metric(
        "Total Matpel",
        (
            len(scheduler_data.mapel)
            if hasattr(scheduler_data, "mapel")
            else "N/A"
        ),
    )
with col_s4:
    st.metric(
        "Tugas Mengajar",
        (
            len(scheduler_data.mengajar)
            if hasattr(scheduler_data, "mengajar")
            else "N/A"
        ),
    )

st.markdown("---")

# ==========================================
# 5. TOMBOL EKSEKUSI GENERATE JADWAL
# ==========================================
if st.button(
    "🚀 Generate Jadwal Sekarang", type="primary", use_container_width=True
):
    with st.spinner("🔍 Menjalankan Optimasi CP-SAT Solver..."):
        if use_fallback:
            # Menggunakan skenario fallback bertahap
            df_jadwal, df_laporan = execute_scheduler_with_fallback(
                scheduler_data
            )
        else:
            # Skenario tunggal
            solver_single = SchedulerSolver(scheduler_data)
            success = solver_single.run_solver(
                timeout_seconds=timeout_sec,
                max_jam_mgmp_nongtt=4,
                max_jp_per_hari=max_jp_daily,
            )
            if success:
                df_jadwal = solver_single.extract_results()
                df_laporan = solver_single.generate_teacher_report(df_jadwal)
            else:
                df_jadwal, df_laporan = pd.DataFrame(), pd.DataFrame()

    # Simpan ke session_state jika hasil ditemukan
    if not df_jadwal.empty:
        st.session_state["df_jadwal_hasil"] = df_jadwal
        st.session_state["df_laporan_guru"] = df_laporan
        st.success("🎉 **Penjadwalan Berhasil Dibuat Tanpa Bentrok!**")
    else:
        st.session_state.pop("df_jadwal_hasil", None)
        st.session_state.pop("df_laporan_guru", None)
        st.error(
            "❌ **Solver Gagal Menemukan Solusi!**\n\n"
            "**Saran Perbaikan:**\n"
            "1. Pastikan fitur **'Gunakan Multi-Skenario Fallback'** di sidebar tetap diaktifkan.\n"
            "2. Naikkan **Batas Max JP Guru / Hari**.\n"
            "3. Periksa ketersediaan jam slot KBM terhadap total JP Rombel."
        )

# ==========================================
# 6. TAMPILAN HASIL & EKSKOR DATA
# ==========================================
if (
    "df_jadwal_hasil" in st.session_state
    and not st.session_state["df_jadwal_hasil"].empty
):
    df_jadwal = st.session_state["df_jadwal_hasil"]
    df_laporan = st.session_state["df_laporan_guru"]

    tab1, tab2, tab3 = st.tabs(
        ["📅 Jadwal Master", "👨‍🏫 Laporan Beban Guru", "📥 Export Hasil"]
    )

    with tab1:
        st.subheader("📌 Matriks Hasil Penjadwalan Utama")

        # Filter Rombel
        rombel_list = (
            sorted(df_jadwal["ID_Rombel"].unique().tolist())
            if "ID_Rombel" in df_jadwal.columns
            else []
        )
        selected_rombel = st.selectbox(
            "Pilih Filter Rombel / Kelas:", ["Semua Rombel"] + rombel_list
        )

        if selected_rombel != "Semua Rombel":
            df_view = df_jadwal[df_jadwal["ID_Rombel"] == selected_rombel]
        else:
            df_view = df_jadwal

        st.dataframe(df_view, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("📊 Rekapitulasi Alokasi Mengajar Guru")
        st.dataframe(df_laporan, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("📥 Unduh Laporan Excel / CSV")

        try:
            # Menggunakan ScheduleExporter yang sudah aman dari KeyError
            excel_bytes = ScheduleExporter.export_to_excel(df_jadwal)

            st.download_button(
                label="📦 Download File Excel (.xlsx)",
                data=excel_bytes,
                file_name="Jadwal_KBM_Sekolah.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as err:
            st.error(f"⚠️ Gagal mengeksport ke file Excel: {err}")
