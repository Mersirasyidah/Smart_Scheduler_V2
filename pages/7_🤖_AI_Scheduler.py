import streamlit as st
import pandas as pd
from scheduler_engine import Scheduler

st.set_page_config(page_title="AI Scheduler Engine", layout="wide")
st.title("🤖 AI Scheduler Engine")

# --- Ambil Data dari Session State atau Database ---
if "guru_df" in st.session_state and "rombel_df" in st.session_state:
    guru_df = st.session_state["guru_df"]
    rombel_df = st.session_state["rombel_df"]
    mengajar_df = st.session_state["mengajar_df"]
    mapel_df = st.session_state["mapel_df"]
    slot_df = st.session_state["slot_df"]

    timeout_seconds = st.slider("Timeout Optimization (detik)", 30, 300, 120)

    if st.button("🚀 Generate Jadwal & Laporan Guru"):
        with st.spinner("Sedang memproses optimasi jadwal..."):
            scheduler = Scheduler(guru_df, rombel_df, mengajar_df, mapel_df, slot_df)
            
            # MEMANGGIL 2 OUTPUT DARI SCHEDULER
            df_hasil, df_laporan_guru = scheduler.generate(timeout=timeout_seconds)

        if not df_hasil.empty:
            st.success("✅ Jadwal & Laporan Berhasil Dibuat!")

            # Menampilkan Hasil dalam 2 Tab
            tab1, tab2 = st.tabs(["📅 Jadwal Master Kelas", "👨‍🏫 Laporan Detail Guru"])

            with tab1:
                st.subheader("Jadwal Mengajar Per Rombel")
                st.dataframe(df_hasil, use_container_width=True)

            with tab2:
                st.subheader("📋 Laporan Detail Harian Guru")
                st.write("Menampilkan status mengajar, kelas yang diampu, jam ke berapa, dan jam kosong sela.")
                
                # Filter Pilihan Guru
                pilihan_guru = st.selectbox(
                    "Filter Guru:",
                    ["SEMUA GURU"] + sorted(df_laporan_guru["ID_Guru"].unique().tolist())
                )

                if pilihan_guru != "SEMUA GURU":
                    df_tampil = df_laporan_guru[df_laporan_guru["ID_Guru"] == pilihan_guru]
                else:
                    df_tampil = df_laporan_guru

                # TABEL LAPORAN GURU YANG DIBUTUHKAN
                st.dataframe(
                    df_tampil,
                    column_config={
                        "ID_Guru": "ID / Nama Guru",
                        "Hari": "Hari",
                        "Status": "Status",
                        "Total_JP": "Total JP",
                        "Detail_Mengajar": "Jam & Kelas Diampu",
                        "Jam_Kosong_Sela": "Jam Kosong / Sela"
                    },
                    use_container_width=True,
                    hide_index=True
                )

                # Download Button Laporan
                csv_laporan = df_laporan_guru.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Laporan Detail Guru (CSV)",
                    data=csv_laporan,
                    file_name="Laporan_Detail_Guru.csv",
                    mime="text/csv"
                )
        else:
            st.error("❌ Solver tidak dapat menemukan kombinasi jadwal yang cocok. Silakan coba lagi.")
else:
    st.info("Silakan muat/upload data master terlebih dahulu sebelum menjalankan scheduler.")
