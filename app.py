import io
import os
import pandas as pd
import streamlit as st
from database import get_all_data

# Import runner & container
try:
    from main import SchedulerContainer, run_scheduler
except ImportError:
    try:
        from solver import SchedulerContainer, run_scheduler
    except ImportError:
        pass

st.set_page_config(
    page_title="AI Scheduler Penjadwalan Sekolah", page_icon="🤖", layout="wide"
)

st.title("🤖 AI Scheduler - Generator Jadwal Otomatis")
st.caption(
    "Optimasi pembuatan jadwal KBM sekolah menggunakan Google OR-Tools CP-SAT Solver."
)

# Inisialisasi session state untuk menyimpan hasil scheduler
if "df_hasil" not in st.session_state:
    st.session_state.df_hasil = None

# ==========================================================
# 1. INISIALISASI & PEMBACAAN DATA
# ==========================================================
st.sidebar.header("📁 Sumber Data Master")
uploaded_file = st.sidebar.file_uploader(
    "Upload File Excel Master (Opsional)", type=["xlsx", "xls"]
)

df_guru = None
df_mapel = None
df_rombel = None
df_guru_mengajar = None
df_hari_jam = None

# OPSI A: Jika Pengguna Unggah File Manual via Sidebar
if uploaded_file is not None:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        sheets = [s.strip() for s in excel_file.sheet_names]

        def read_clean(sheet_name):
            df = pd.read_excel(excel_file, sheet_name)
            df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
            return df

        df_guru = read_clean("Guru")
        df_mapel = read_clean("Mapel")
        df_rombel = read_clean("Rombel" if "Rombel" in sheets else "Kelas")

        sheet_mengajar = (
            "Guru_Mengajar" if "Guru_Mengajar" in sheets else "Mengajar"
        )
        df_guru_mengajar = read_clean(sheet_mengajar)

        sheet_slot = "Hari_Jam" if "Hari_Jam" in sheets else "Slot"
        df_hari_jam = read_clean(sheet_slot)

        st.sidebar.success("✅ File Excel unggahan berhasil dimuat!")
    except Exception as e:
        st.sidebar.error(f"❌ Gagal membaca file upload: {e}")

# OPSI B: Jika Tidak Upload, Ambil Otomatis dari database.py
if df_guru is None:
    try:
        data_dict = get_all_data()
        if data_dict:
            df_guru = data_dict.get("guru")
            df_mapel = data_dict.get("mapel")
            df_rombel = data_dict.get("rombel")
            df_guru_mengajar = data_dict.get("mengajar")
            df_hari_jam = data_dict.get("slot")
            st.sidebar.info("ℹ️ Menggunakan Data Master Lokal.")
    except Exception as e:
        st.sidebar.warning(f"⚠️ Gagal mengambil data lokal: {e}")

timeout_user = st.sidebar.slider(
    "Total Durasi Timeout Solver (Detik)", 30, 300, 120, 30
)

# ==========================================================
# 2. GUARD CLAUSE (VALIDASI KELENGKAPAN DATA)
# ==========================================================
data_ready = all(
    df is not None and not df.empty
    for df in [
        df_guru,
        df_mapel,
        df_rombel,
        df_guru_mengajar,
        df_hari_jam,
    ]
)

if not data_ready:
    st.error("⚠️ **Data Master Belum Siap!**")
    st.warning(
        "Silakan pastikan file `database_scheduler.xlsx` ada di folder proyek "
        "atau unggah file Excel melalui menu di sidebar kiri."
    )
    st.stop()

# ==========================================================
# 3. PROSES PENJADWALAN
# ==========================================================
st.success("🎉 Data Master Terdeteksi Lengkap & Siap Digunakan!")

if st.button("🚀 Proses Penjadwalan Otomatis", type="primary"):
    with st.spinner("Sedang memproses dan mengoptimasi jadwal pembelajaran..."):
        try:
            res = run_scheduler(
                df_guru=df_guru,
                df_mapel=df_mapel,
                df_rombel=df_rombel,
                df_guru_mengajar=df_guru_mengajar,
                df_hari_jam=df_hari_jam,
                timeout=timeout_user,
            )
            # Menangani pengembalian tuple atau dataframe langsung
            if isinstance(res, tuple):
                st.session_state.df_hasil = res[0]
            else:
                st.session_state.df_hasil = res
        except Exception as e:
            st.error(f"❌ Error saat menjalankan solver: {e}")
            st.session_state.df_hasil = None

# ==========================================================
# 4. TAMPILAN HASIL PENJADWALAN
# ==========================================================
df_hasil = st.session_state.df_hasil

if df_hasil is not None and not df_hasil.empty:
    st.success("🎉 **BERHASIL!** AI Solver menemukan jadwal optimal.")

    # Deteksi Nama Kolom secara Dinamis
    col_rombel = "ID_Rombel" if "ID_Rombel" in df_hasil.columns else "Kelas"
    col_guru = (
        "Nama_Guru"
        if "Nama_Guru" in df_hasil.columns
        else ("Nama Guru" if "Nama Guru" in df_hasil.columns else "ID_Guru")
    )
    col_mapel = (
        "Nama_Mapel"
        if "Nama_Mapel" in df_hasil.columns
        else ("Nama Mapel" if "Nama Mapel" in df_hasil.columns else "ID_Mapel")
    )
    col_jam = (
        "Jam_Ke"
        if "Jam_Ke" in df_hasil.columns
        else ("Jam" if "Jam" in df_hasil.columns else "Jam_Ke")
    )

    # Gabungkan Guru + Mapel untuk isi cell matriks
    df_hasil_display = df_hasil.copy()
    df_hasil_display["Guru_Mapel"] = (
        df_hasil_display[col_guru].astype(str)
        + "\n("
        + df_hasil_display[col_mapel].astype(str)
        + ")"
    )

    # Pivot Matriks Rombel
    pivot_rombel = df_hasil_display.pivot_table(
        index=["Hari", col_jam],
        columns=col_rombel,
        values="Guru_Mapel",
        aggfunc=lambda x: " / ".join(x),
        observed=False,
    ).fillna("-")

    tab1, tab2 = st.tabs(["📊 Matriks Jadwal Rombel", "📝 Detail Tabel Jadwal"])

    with tab1:
        st.dataframe(pivot_rombel, use_container_width=True)

    with tab2:
        st.dataframe(
            df_hasil_display.drop(columns=["Guru_Mapel"], errors="ignore"),
            use_container_width=True,
        )

    # File Download Excel Multi-Sheet
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_hasil_display.drop(columns=["Guru_Mapel"], errors="ignore").to_excel(
            writer, sheet_name="Jadwal_Detail", index=False
        )
        pivot_rombel.to_excel(writer, sheet_name="Matriks_Kelas")

    st.download_button(
        label="📥 Download Hasil Jadwal Lengkap (.xlsx)",
        data=output.getvalue(),
        file_name="Hasil_Jadwal_Pelajaran.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
elif df_hasil is not None and df_hasil.empty:
    st.error(
        "❌ **Gagal menemukan solusi jadwal.** Cobalah menaikkan nilai Timeout di sidebar "
        "atau cek kembali bentrokan/kelonggaran di data master."
    )
