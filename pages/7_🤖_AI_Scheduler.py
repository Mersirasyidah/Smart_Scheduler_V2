import streamlit as st
import pandas as pd
import sqlite3
import os
from scheduler_engine import Scheduler

st.set_page_config(page_title="AI Scheduler Engine", layout="wide")
st.title("🤖 AI Scheduler Engine")

def auto_load_data():
    """Fungsi otomatis untuk mengambil data dari Database SQLite atau Folder Data"""
    # 1. Coba Ambil dari Database SQLite (jika aplikasi Anda pakai DB)
    db_paths = ["database.db", "data/database.db", "smart_scheduler.db"]
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                st.session_state["guru_df"] = pd.read_sql_query("SELECT * FROM guru", conn)
                st.session_state["rombel_df"] = pd.read_sql_query("SELECT * FROM rombel", conn)
                st.session_state["mengajar_df"] = pd.read_sql_query("SELECT * FROM mengajar", conn)
                st.session_state["mapel_df"] = pd.read_sql_query("SELECT * FROM mapel", conn)
                st.session_state["slot_df"] = pd.read_sql_query("SELECT * FROM slot", conn)
                conn.close()
                return True
            except Exception:
                pass

    # 2. Coba Ambil dari File CSV di folder data/
    try:
        st.session_state["guru_df"] = pd.read_csv("data/guru.csv")
        st.session_state["rombel_df"] = pd.read_csv("data/rombel.csv")
        st.session_state["mengajar_df"] = pd.read_csv("data/mengajar.csv")
        st.session_state["mapel_df"] = pd.read_csv("data/mapel.csv")
        st.session_state["slot_df"] = pd.read_csv("data/slot.csv")
        return True
    except Exception:
        pass

    # 3. Coba Ambil dari database.py jika ada fungsi khusus getter
    try:
        import database as db
        st.session_state["guru_df"] = db.get_guru()
        st.session_state["rombel_df"] = db.get_rombel()
        st.session_state["mengajar_df"] = db.get_mengajar()
        st.session_state["mapel_df"] = db.get_mapel()
        st.session_state["slot_df"] = db.get_slot()
        return True
    except Exception:
        pass

    return False

# Jalankan auto-load jika session_state belum berisi data
if "guru_df" not in st.session_state or st.session_state["guru_df"] is None:
    auto_load_data()

# --- CEK KETERSEDIAAN DATA ---
if "guru_df" in st.session_state and st.session_state["guru_df"] is not None and not st.session_state["guru_df"].empty:
    guru_df = st.session_state["guru_df"]
    rombel_df = st.session_state["rombel_df"]
    mengajar_df = st.session_state["mengajar_df"]
    mapel_df = st.session_state["mapel_df"]
    slot_df = st.session_state["slot_df"]

    st.success("✅ Data Master Berhasil Dimuat!")
    timeout_seconds = st.slider("Timeout Optimization (detik)", 30, 300, 120)

    if st.button("🚀 Generate Jadwal & Laporan Guru"):
        with st.spinner("Sedang memproses optimasi jadwal..."):
            scheduler = Scheduler(guru_df, rombel_df, mengajar_df, mapel_df, slot_df)
            df_hasil, df_laporan_guru = scheduler.generate(timeout=timeout_seconds)

        if not df_hasil.empty:
            st.success("✅ Jadwal & Laporan Berhasil Dibuat!")

            tab1, tab2 = st.tabs(["📅 Jadwal Master Kelas", "👨‍🏫 Laporan Detail Guru"])

            with tab1:
                st.subheader("Jadwal Mengajar Per Rombel")
                st.dataframe(df_hasil, use_container_width=True)

            with tab2:
                st.subheader("📋 Laporan Detail Harian Guru")
                
                pilihan_guru = st.selectbox(
                    "Filter Guru:",
                    ["SEMUA GURU"] + sorted(df_laporan_guru["ID_Guru"].unique().tolist())
                )

                if pilihan_guru != "SEMUA GURU":
                    df_tampil = df_laporan_guru[df_laporan_guru["ID_Guru"] == pilihan_guru]
                else:
                    df_tampil = df_laporan_guru

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

                csv_laporan = df_laporan_guru.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Laporan Detail Guru (CSV)",
                    data=csv_laporan,
                    file_name="Laporan_Detail_Guru.csv",
                    mime="text/csv"
                )
        else:
            st.error("❌ Solver gagal menemukan kombinasi jadwal. Coba naikkan durasi Timeout.")
else:
    st.warning("⚠️ Data Master belum dimuat ke memori.")
    st.info("📌 **Cara Mengatasi:** Buka menu **Data Input / Upload / Database** di sidebar terlebih dahulu untuk memuat data master, lalu kembali ke halaman ini.")
