import streamlit as st
import pandas as pd
from scheduler_engine import SmartSchedulerEngine

st.set_page_config(page_title="Smart Scheduler V2", layout="wide")

st.title("⚡ Smart Scheduler V2")
st.subheader("Sistem Penjadwalan Otomatis Berbasis Constraints")

uploaded_file = st.sidebar.file_uploader("Unggah File Database (database_scheduler.xlsx)", type=["xlsx"])

if uploaded_file or st.sidebar.button("Gunakan File Default"):
    file_path = uploaded_file if uploaded_file else "database_scheduler.xlsx"
    
    with st.spinner("Menyusun Jadwal Otomatis..."):
        engine = SmartSchedulerEngine(file_path)
        results = engine.run()

    tab1, tab2, tab3 = st.tabs(["📌 Matriks Per Kelas", "📋 Detail Jadwal", "⚠️ Unassigned"])

    with tab1:
        st.write("### Jadwal Pelajaran per Kelas")
        st.dataframe(results['class_matrix'], use_container_width=True)

    with tab2:
        st.write("### Daftar Master Jadwal")
        st.dataframe(results['df_schedule'], use_container_width=True)

    with tab3:
        st.write("### Item yang Gagal Masuk Jadwal")
        if results['unassigned']:
            st.warning(f"Ada {len(results['unassigned'])} blok jam yang tidak mendapat slot.")
            st.write(pd.DataFrame(results['unassigned']))
        else:
            st.success("Semua jadwal berhasil diplot 100% tanpa bentrok!")
