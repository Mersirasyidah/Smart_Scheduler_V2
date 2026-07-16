# app.py
import streamlit as st
from database import load_database

st.set_page_config(
    page_title="Smart Scheduler V2",
    page_icon="📚",
    layout="wide"
)

db = load_database()

st.title("📚 SMART SCHEDULER V2")
st.subheader("Sistem Penyusunan Jadwal Pembelajaran SMP")
st.divider()

st.header("📂 Database")
st.write("Sheet yang berhasil dideteksi:")
for sheet in db.keys():
    st.success(f"✔️ Sheet: {sheet}")

st.divider()

st.header("📊 Dashboard Statistik")
col1, col2, col3 = st.columns(3)

jumlah_guru = len(db["Guru"]) if "Guru" in db else 0
jumlah_mapel = len(db["Mapel"]) if "Mapel" in db else 0
jumlah_rombel = len(db["Rombel"]) if "Rombel" in db else 0

col1.metric("👨‍🏫 Total Guru", jumlah_guru)
col2.metric("📖 Total Mata Pelajaran", jumlah_mapel)
col3.metric("🏫 Total Rombel", jumlah_rombel)
