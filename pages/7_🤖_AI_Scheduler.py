import streamlit as st
import pandas as pd
import sqlite3
import os
from scheduler_engine import Scheduler

st.set_page_config(page_title="AI Scheduler Engine", page_icon="🤖", layout="wide")
st.title("🤖 AI Scheduler Engine")

# 1. Inisialisasi Key Session State untuk Mencegah KeyError
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
                
                # Coba baca tabel mengajar atau guru_mengajar
                try:
                    st.session_state["mengajar_df"] = pd.read_sql_query("SELECT * FROM mengajar", conn)
                except Exception:
                    st.session_state["mengajar_df"] = pd.read_sql_query("SELECT * FROM guru_mengajar", conn)
                    
                st.session_state["mapel_df"] = pd.read_sql_query("SELECT * FROM mapel", conn)
                st.session_state["slot_df"] = pd.read_sql_query("SELECT * FROM slot", conn)
                conn.close()
                return True
            except Exception:
                pass
    return False

def load_data_from_files():
    """Mencoba membaca file CSV dari folder data/"""
    try:
        st.session_state["guru_df"] = pd.read_csv("data/guru.csv")
        st.session_state["rombel_df"] = pd.read_csv("data/rombel.csv")
        
        # Coba mengajar.csv atau guru_mengajar.csv
        if os.path.exists("data/mengajar.csv"):
            st.session_state["mengajar_df"] = pd.read_csv("data/mengajar.csv")
        elif os.path.exists("data/guru_mengajar.csv"):
            st.session_state["mengajar_df"] = pd.read_csv("data/guru_mengajar.csv")

        st.session_state["mapel_df"] = pd.read_csv("data/mapel.csv")
        st.session_state["slot_df"] = pd.read_csv("data/slot.csv")
        return True
    except Exception:
        pass
    return False

def is_data_ready():
    """Memeriksa apakah semua data master di session state sudah terisi"""
    return all(st.session_state.get(k) is not None and not st.session_state.get(k).empty for k in REQUIRED_KEYS)

# Auto Load Data jika belum siap di memori
if not is_data_ready():
    if not load_data_from_database():
        load_data_from_files()

# --- TAMPILAN UTAMA APLIKASI ---
if is_data_ready():
    st.success("✅ Semua Data Master Berhasil Dimuat!")

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
                
                if not df_laporan_guru.empty and "ID_Guru" in df_laporan_guru.columns:
                    daftar_guru = sorted(df_laporan_guru["ID_Guru"].dropna().unique().tolist())
                    pilihan_guru = st.selectbox("Filter Guru:", ["SEMUA GURU"] + daftar_guru)

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
                    st.info("Laporan detail guru belum tersedia untuk hasil jadwal ini.")
        else:
            st.error("❌ Solver tidak dapat menemukan kombinasi jadwal yang cocok. Silakan naikkan batas Timeout atau periksa kembali kecukupan slot waktu vs total JP mengajar.")

else:
    st.warning("⚠️ Data Master belum lengkap di memori. Unggah file Excel master di bawah ini:")
    
    uploaded_file = st.file_uploader("Upload Excel Data Master", type=["xlsx", "xls"])
    if uploaded_file is not None:
        try:
            excel = pd.ExcelFile(uploaded_file)
            sheet_names = excel.sheet_names

            # Helper function untuk mencari nama sheet secara fleksibel
            def read_sheet_flexibly(target_names):
                for sheet in sheet_names:
                    norm_sheet = sheet.lower().replace("_", "").replace(" ", "")
                    for target in target_names:
                        norm_target = target.lower().replace("_", "").replace(" ", "")
                        if norm_sheet == norm_target:
                            return pd.read_excel(excel, sheet)
                return None

            # Pembacaan fleksibel untuk setiap sheet
            st.session_state["guru_df"] = read_sheet_flexibly(["Guru"])
            st.session_state["rombel_df"] = read_sheet_flexibly(["Rombel", "Kelas"])
            
            # Toleran terhadap nama sheet: Mengajar, Guru_Mengajar, Guru Mengajar, dll.
            st.session_state["mengajar_df"] = read_sheet_flexibly(["Mengajar", "Guru_Mengajar", "GuruMengajar"])
            
            st.session_state["mapel_df"] = read_sheet_flexibly(["Mapel", "Mata_Pelajaran"])
            st.session_state["slot_df"] = read_sheet_flexibly(["Slot", "Slot_Waktu", "Jadwal"])

            # Cek sheet yang belum ditemukan
            missing_keys = [k for k in REQUIRED_KEYS if st.session_state[k] is None]
            
            if missing_keys:
                st.error(f"❌ Kunci data berikut belum ditemukan di Excel: {missing_keys}. Pastikan sheet memuat data Guru, Rombel, Mengajar/Guru_Mengajar, Mapel, dan Slot.")
            else:
                st.success("✅ File Excel berhasil diunggah dan seluruh sheet terbaca dengan sempurna!")
                st.rerun()

        except Exception as e:
            st.error(f"Gagal membaca file Excel: {e}")
