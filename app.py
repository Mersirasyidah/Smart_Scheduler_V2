import streamlit as st
from database import DatabaseManager

st.set_page_config(
    page_title="Smart Scheduler V2",
    page_icon="📅",
    layout="wide"
)

st.title("⚡ Smart Scheduler V2")
st.subheader("Sistem Penjadwalan Otomatis Berbasis AI")

st.markdown("""
Selamat datang di **Smart Scheduler V2**. 
Gunakan navigasi di sebelah kiri untuk melihat data atau menjalankan generator jadwal AI.
""")

# Load and Preview Data
db = DatabaseManager()
try:
    data = db.load_all_data()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Guru", len(data["guru"]))
    col2.metric("Total Mapel", len(data["mapel"]))
    col3.metric("Total Rombel", len(data["rombel"]))
    
    st.divider()
    st.subheader("📋 Ringkasan Alokasi Jam Mengajar")
    st.dataframe(data["guru_mengajar"].head(10), use_container_width=True)
except Exception as e:
    st.error(f"Gagal memuat database: {e}")
