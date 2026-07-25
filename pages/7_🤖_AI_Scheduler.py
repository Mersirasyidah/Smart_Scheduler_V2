import streamlit as st
import pandas as pd
import io
from scheduler_engine import Scheduler
from scheduler_core.exporter import ScheduleExporter

st.set_page_config(page_title="AI Schedule Generator", page_icon="🤖", layout="wide")

st.title("🤖 AI Automatic Schedule Generator")
st.write("Sistem Pembuat Jadwal Pelajaran Otomatis Bebas Bentrok dan Sesuai Aturan KBM.")

target_file = st.sidebar.text_input("File Database Excel", value="database_scheduler.xlsx")

col_btn1, col_btn2 = st.columns([2, 8])
with col_btn1:
    btn_generate = st.button("🚀 Generate Jadwal Sekarang", type="primary", use_container_width=True)

# --- PROSES GENERATE JADWAL ---
if btn_generate or 'results' in st.session_state:
    if btn_generate:
        with st.spinner("Sedang mengoptimalkan jadwal... Mohon tunggu."):
            try:
                engine = Scheduler(target_file)
                st.session_state['results'] = engine.run()
                st.success("Jadwal berhasil disusun!")
            except Exception as e:
                st.error(f"Terjadi kesalahan saat memproses data: {e}")
                st.stop()

    # Ambil hasil dari session state
    results = st.session_state['results']
    df_schedule = results.get('df_schedule', pd.DataFrame())
    unassigned = results.get('unassigned', [])

    # Matriks 1: Nama Guru
    matrix_nama = ScheduleExporter.create_class_matrix_by_name(df_schedule)
    # Matriks 2: Kode Mapel
    matrix_kode = ScheduleExporter.create_class_matrix_by_code(df_schedule)

    # --- METRIK SUMMARY ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Slot Terisi", len(df_schedule))
    with m2:
        st.metric("Jumlah Kelas", df_schedule['Kelas'].nunique() if not df_schedule.empty else 0)
    with m3:
        st.metric("Jumlah Guru", df_schedule['ID Guru'].nunique() if not df_schedule.empty else 0)
    with m4:
        st.metric("Gagal Dijadwalkan", len(unassigned), delta_color="inverse")

    st.markdown("---")

    # --- TAMPILAN TAB HASIL ---
    tab_nama, tab_kode, tab_detail, tab_unassigned = st.tabs([
        "👤 Matriks (Nama Guru)", 
        "🔢 Matriks (Kode Mapel)", 
        "📋 Master List", 
        "⚠️ Unassigned"
    ])

    with tab_nama:
        st.subheader("1. Tampilan Matriks: Singkatan Mapel & Nama Depan Guru")
        st.write("Contoh Tampilan: `IPA (Purwanto)`")
        st.dataframe(matrix_nama, use_container_width=True)

    with tab_kode:
        st.subheader("2. Tampilan Matriks: Kode Mapel & ID Guru")
        st.write("Contoh Tampilan: `M11 (G14)`")
        st.dataframe(matrix_kode, use_container_width=True)

    with tab_detail:
        st.subheader("Master List Detail Jadwal")
        st.dataframe(df_schedule, use_container_width=True)

    with tab_unassigned:
        st.subheader("Daftar Jam Mengajar yang Gagal Dijadwalkan")
        if unassigned:
            st.warning(f"Terdapat {len(unassigned)} alokasi jam mengajar yang belum mendapatkan slot.")
            st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
        else:
            st.success("🎉 Luar biasa! Semua jadwal 100% berhasil di-plot tanpa unassigned.")

    # --- EXPORT KE EXCEL ---
    st.markdown("---")
    st.subheader("📥 Export Hasil Jadwal ke Excel")
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        matrix_nama.to_excel(writer, sheet_name='Matriks_Nama_Guru')
        matrix_kode.to_excel(writer, sheet_name='Matriks_Kode_Mapel')
        df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
        if unassigned:
            pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)
            
    st.download_button(
        label="📥 Download Hasil Jadwal (Excel)",
        data=buffer.getvalue(),
        file_name="Hasil_Jadwal_Pelajaran.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
