import sys
import os
import io
import streamlit as st
import pandas as pd

# 1. Mengatasi ImportError saat di-deploy ke Streamlit Cloud
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import modul lokal
try:
    from scheduler_engine import Scheduler
except ImportError:
    st.error("Gagal mengimpor modul `scheduler_engine`. Pastikan file `scheduler_engine.py` ada di direktori utama.")
    st.stop()

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="AI Scheduler V2",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 AI Smart Scheduler V2")
st.markdown("Generator Jadwal Otomatis berbasis Constraint-Solver.")

# --- SIDEBAR: INPUT & PENGATURAN ---
st.sidebar.header("⚙️ Pengaturan Data")

default_excel = "database_scheduler.xlsx"
uploaded_file = st.sidebar.file_uploader(
    "Unggah File Database Excel (.xlsx)", 
    type=["xlsx"]
)

# Menentukan lokasi file yang dipakai
if uploaded_file is not None:
    target_file = uploaded_file
    st.sidebar.success("File kustom berhasil diunggah!")
else:
    target_file = default_excel
    st.sidebar.info("Menggunakan database default (`database_scheduler.xlsx`).")

btn_generate = st.sidebar.button("🚀 Jalankan Generator Jadwal", type="primary", use_container_width=True)

# --- PROSES GENERATE JADWAL ---
if btn_generate or 'results' in st.session_state:
    if btn_generate:
        with st.spinner("Sedang menyusun jadwal tanpa bentrok... Mohon tunggu."):
            try:
                engine = Scheduler(target_file)
                st.session_state['results'] = engine.run()
                st.success("Jadwal berhasil disusundengan sukses!")
            except Exception as e:
                st.error(f"Terjadi kesalahan saat memproses data: {e}")
                st.stop()

    results = st.session_state['results']
    df_schedule = results.get('df_schedule', pd.DataFrame())
    class_matrix = results.get('class_matrix', pd.DataFrame())
    unassigned = results.get('unassigned', [])

    # --- RINGKASAN METRIK ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Slot Terisi", len(df_schedule))
    with col2:
        st.metric("Jumlah Kelas Scheduled", df_schedule['Kelas'].nunique() if not df_schedule.empty else 0)
    with col3:
        st.metric("Jumlah Guru Terlibat", df_schedule['ID Guru'].nunique() if not df_schedule.empty else 0)
    with col4:
        st.metric("Gagal Dijadwalkan", len(unassigned), delta_color="inverse")

    st.markdown("---")

    # --- TABS REKAPITULASI ---
    tab_matrix, tab_detail, tab_filter, tab_unassigned = st.tabs([
        "📊 Matriks Jadwal Kelas", 
        "📋 Master List", 
        "🔍 Filter Jadwal",
        "⚠️ Unassigned Slot"
    ])

    # TAB 1: Matriks per Kelas
    with tab_matrix:
        st.subheader("Matriks Jadwal per Kelas (Hari & Jam)")
        if not class_matrix.empty:
            st.dataframe(class_matrix, use_container_width=True)
        else:
            st.info("Belum ada data matriks.")

    # TAB 2: Detail Master List
    with tab_detail:
        st.subheader("Daftar Detail Hasil Penjadwalan")
        if not df_schedule.empty:
            st.dataframe(df_schedule, use_container_width=True)
            
            # Fitur Unduh Excel Hasil
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_schedule.to_excel(writer, sheet_name='Master_Jadwal', index=False)
                if not class_matrix.empty:
                    class_matrix.to_excel(writer, sheet_name='Matriks_Kelas')
            excel_data = output.getvalue()

            st.download_button(
                label="📥 Unduh Hasil Jadwal (.xlsx)",
                data=excel_data,
                file_name="Hasil_Jadwal_SmartScheduler.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Belum ada data jadwal.")

    # TAB 3: Filter Jadwal Spesifik
    with tab_filter:
        st.subheader("Filter Jadwal Berdasarkan Kelas / Guru")
        if not df_schedule.empty:
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                selected_kelas = st.selectbox("Pilih Kelas:", ["Semua"] + list(df_schedule['Kelas'].unique()))
            with f_col2:
                selected_guru = st.selectbox("Pilih Guru:", ["Semua"] + list(df_schedule['Nama Guru'].unique()))

            filtered_df = df_schedule.copy()
            if selected_kelas != "Semua":
                filtered_df = filtered_df[filtered_df['Kelas'] == selected_kelas]
            if selected_guru != "Semua":
                filtered_df = filtered_df[filtered_df['Nama Guru'] == selected_guru]

            st.dataframe(filtered_df, use_container_width=True)
        else:
            st.info("Belum ada data untuk difilter.")

    # TAB 4: Unassigned Slot
    with tab_unassigned:
        st.subheader("Daftar Mengajar yang Gagal Dijadwalkan")
        if unassigned:
            st.warning("Pelajaran di bawah ini tidak dapat dimasukkan ke jadwal karena bentrok constraint atau kekurangan slot waktu yang cukup.")
            st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
        else:
            st.success("🎉 Luar biasa! Semua alokasi jam mengajar 100% berhasil masuk ke dalam jadwal tanpa ada yang gagal.")

else:
    st.info("👈 Klik tombol **'Jalankan Generator Jadwal'** pada sidebar di sebelah kiri untuk memulai penyusunan jadwal otomatis.")
