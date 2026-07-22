import streamlit as st
import pandas as pd
import sqlite3
import os
from scheduler_engine import Scheduler

st.set_page_config(page_title="AI Scheduler Engine", layout="wide")
st.title("🤖 AI Scheduler Engine")

# 1. Inisialisasi Key Session State Agar Tidak Terjadi KeyError
REQUIRED_KEYS = ["guru_df", "rombel_df", "mengajar_df", "mapel_df", "slot_df"]
for key in REQUIRED_KEYS:
    if key not in st.session_state:
        st.session_state[key] = None

def load_data_from_database():
    """Mencoba membaca data dari SQLite jika ada"""
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
    return False

def load_data_from_files():
    """Mencoba membaca file CSV/Excel dari folder data/"""
    try:
        st.session_state["guru_df"] = pd.read_csv("data/guru.csv")
        st.session_state["rombel_df"] = pd.read_csv("data/rombel.csv")
        st.session_state["mengajar_df"] = pd.read_csv("data/mengajar.csv")
        st.session_state["mapel_df"] = pd.read_csv("data/mapel.csv")
        st.session_state["slot_df"] = pd.read_csv("data/slot.csv")
        return True
    except Exception:
        pass
    return False

# Cek apakah data sudah lengkap di memori
def is_data_ready():
    return all(st.session_state.get(k) is not None and not st.session_state.get(k).empty for k in REQUIRED_KEYS)

# Auto Load jika data belum ada
if not is_data_ready():
    if not load_data_from_database():
        load_data_from_files()

# --- TAMPILAN UTAMA ---
if is_data_ready():
    st.success("✅ Semua Data Master Berhasil Dimuat!")

    # Mengambil dataframe dengan aman
    guru_df = st.session_state["guru_df"]
    rombel_df = st.session_state["rombel_df"]
    mengajar_df = st.session_state["mengajar_df"]
    mapel_df = st.session_state["mapel_df"]
    slot_df = st.session_state["slot_df"]

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
            st.error("❌ Solver gagal menemukan kombinasi jadwal. Silakan naikkan durasi Timeout.")

else:
    st.warning("⚠️ Data Master belum lengkap di memori. Unggah file Excel gabungan (yang berisi sheet Guru, Rombel, Mengajar, Mapel, Slot) di bawah ini:")
    
    uploaded_file = st.file_uploader("Upload Excel Data Master", type=["xlsx", "xls"])
    if uploaded_file is not None:
        try:
            excel = pd.ExcelFile(uploaded_file)
            st.session_state["guru_df"] = pd.read_excel(excel, "Guru")
            st.session_state["rombel_df"] = pd.read_excel(excel, "Rombel")
            st.session_state["mengajar_df"] = pd.read_excel(excel, "Mengajar")
            st.session_state["mapel_df"] = pd.read_excel(excel, "Mapel")
            st.session_state["slot_df"] = pd.read_excel(excel, "Slot")
            st.success("✅ File berhasil diunggah! Klik tombol Rerun atau refresh halaman.")
            st.rerun()
        except Exception as e:
            st.error(f"Gagal membaca sheet dari Excel: {e}")
