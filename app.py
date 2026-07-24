import io
import os
import pandas as pd
import streamlit as st
from database import get_all_data

# Import runner & container milikmu
try:
    from main import SchedulerContainer, run_scheduler
except ImportError:
    # Fallback jika runner ada di file lokal yang sama / solver
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

# ==========================================================
# 1. INISIALISASI & PEMBACAAN DATA
# ==========================================================
st.sidebar.header("📁 Sumber Data Master")
uploaded_file = st.sidebar.file_uploader(
    "Upload File Excel Master (Opsional)", type=["xlsx", "xls"]
)

# Variable penampung DataFrame
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
    data_dict = get_all_data()
    if data_dict:
        df_guru = data_dict["guru"]
        df_mapel = data_dict["mapel"]
        df_rombel = data_dict["rombel"]
        df_guru_mengajar = data_dict["mengajar"]
        df_hari_jam = data_dict["slot"]
        st.sidebar.info("ℹ️ Menggunakan Data Master Lokal.")

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
    with st.spinner(
        "Sedang memproses dan mengoptimasi jadwal pembelajaran..."
    ):

        # Memanggil fungsi run_scheduler milikmu
        df_hasil = run_scheduler(
            df_guru=df_guru,
            df_mapel=df_mapel,
            df_rombel=df_rombel,
            df_guru_mengajar=df_guru_mengajar,
            df_hari_jam=df_hari_jam,
            timeout=timeout_user,
        )

        if not df_hasil.empty:
            st.success("🎉 **BERHASIL!** AI Solver menemukan jadwal optimal.")

            # Buat Tampilan Pivot Matriks Rombel
            col_rombel = (
                "ID_Rombel" if "ID_Rombel" in df_hasil.columns else "Kelas"
            )
            col_guru = "ID_Guru" if "ID_Guru" in df_hasil.columns else "Guru"
            col_mapel = "ID_Mapel" if "ID_Mapel" in df_hasil.columns else "Mapel"

            df_hasil["Guru_Mapel"] = (
                df_hasil[col_guru].astype(str)
                + " ("
                + df_hasil[col_mapel].astype(str)
                + ")"
            )

            pivot_rombel = df_hasil.pivot_table(
                index=["Hari", "Jam_Ke"],
                columns=col_rombel,
                values="Guru_Mapel",
                aggfunc=lambda x: "/".join(x),
                observed=False,
            ).fillna("-")

            tab1, tab2 = st.tabs(
                ["📊 Matriks Jadwal Rombel", "📝 Detail Tabel Jadwal"]
            )

            with tab1:
                st.dataframe(pivot_rombel, use_container_width=True)

            with tab2:
                st.dataframe(
                    df_hasil.drop(columns=["Guru_Mapel"], errors="ignore"),
                    use_container_width=True,
                )

            # File Download Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_hasil.drop(columns=["Guru_Mapel"], errors="ignore").to_excel(
                    writer, sheet_name="Jadwal_Detail", index=False
                )
                pivot_rombel.to_excel(writer, sheet_name="Matriks_Kelas")

            st.download_button(
                label="📥 Download Hasil Jadwal Lengkap (.xlsx)",
                data=output.getvalue(),
                file_name="Hasil_Jadwal_Pelajaran.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.error(
                "❌ **Gagal menemukan solusi jadwal.** Cobalah menaikkan nilai Timeout di sidebar "
                "atau cek kembali bentrokan jam mengajar di data Excel."
            )
