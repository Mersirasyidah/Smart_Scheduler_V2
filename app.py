import io
import pandas as pd
import streamlit as st
from database import (
    get_guru,
    get_mapel,
    get_mengajar,
    get_rombel,
    get_slot,
)
from solver import SchedulerSolver

st.set_page_config(
    page_title="Sistem Penjadwalan Sekolah", page_icon="🤖", layout="wide"
)

st.title("🤖 AI Scheduler - Generator Jadwal Otomatis")
st.caption(
    "Optimasi pembuatan jadwal KBM menggunakan Google OR-Tools CP-SAT Solver."
)


# Wrapper Class Data
class SchedulerData:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df


# Inisialisasi Session State Data Master
if "scheduler_data" not in st.session_state:
    st.session_state["scheduler_data"] = None

# Sidebar
st.sidebar.header("📁 Unggah / Pilihan Data")
source_option = st.sidebar.radio(
    "Pilih Sumber Data:", ["Database Default Excel", "Unggah File Excel Baru"]
)

if source_option == "Unggah File Excel Baru":
    uploaded_file = st.sidebar.file_uploader(
        "Upload File Excel Master", type=["xlsx", "xls"]
    )
    if uploaded_file:
        try:
            excel_file = pd.ExcelFile(uploaded_file)
            guru_df = pd.read_excel(excel_file, "Guru")
            rombel_df = pd.read_excel(excel_file, "Rombel")
            mengajar_df = pd.read_excel(excel_file, "Mengajar")
            mapel_df = pd.read_excel(excel_file, "Mapel")
            slot_df = pd.read_excel(excel_file, "Slot")

            st.session_state["scheduler_data"] = SchedulerData(
                guru_df, rombel_df, mengajar_df, mapel_df, slot_df
            )
            st.sidebar.success("✅ File Excel unggahan berhasil dibaca.")
        except Exception as e:
            st.sidebar.error(f"❌ Gagal membaca file: {e}")
else:
    # Mengambil dari database.py
    try:
        guru_df = get_guru()
        rombel_df = get_rombel()
        mengajar_df = get_mengajar()
        mapel_df = get_mapel()
        slot_df = get_slot()

        if not (guru_df.empty or mengajar_df.empty or slot_df.empty):
            st.session_state["scheduler_data"] = SchedulerData(
                guru_df, rombel_df, mengajar_df, mapel_df, slot_df
            )
            st.sidebar.success("✅ Database lokal siap digunakan.")
        else:
            st.session_state["scheduler_data"] = None
    except Exception as e:
        st.sidebar.error(f"❌ Error database: {e}")

timeout_user = st.sidebar.slider(
    "Total Durasi Timeout Solver (Detik)", 30, 300, 120, 30
)

# Guard Clause Pengecekan Ketersediaan Data
if st.session_state["scheduler_data"] is None:
    st.warning("⚠️ **Data Master Belum Siap!**")
    st.info(
        "Silakan pastikan file `data/database_scheduler.xlsx` tersedia atau unggah file Excel di sidebar kiri."
    )
    st.stop()

# ==========================================================
# PROSES EKSEKUSI GENERATOR
# ==========================================================
scheduler_data = st.session_state["scheduler_data"]
st.success("🎉 Data Master (Guru, Rombel, Mengajar, Mapel, Slot) Siap!")

if st.button("🚀 Proses Penjadwalan Otomatis", type="primary"):

    skenario_list = [
        {
            "desc": "Skenario 1 (Ideal): Max 6 JP/Hari | MGMP Non-GTT Max Jam Ke-4",
            "max_jp": 6,
            "max_mgmp": 4,
        },
        {
            "desc": "Skenario 2 (Fleksibel): Max 6 JP/Hari | MGMP Non-GTT Max Jam Ke-3",
            "max_jp": 6,
            "max_mgmp": 3,
        },
        {
            "desc": "Skenario 3 (Relaksasi JP): Max 7 JP/Hari | MGMP Non-GTT Max Jam Ke-4",
            "max_jp": 7,
            "max_mgmp": 4,
        },
        {
            "desc": "Skenario 4 (Emergency): Max 8 JP/Hari | MGMP Non-GTT Max Jam Ke-5",
            "max_jp": 8,
            "max_mgmp": 5,
        },
    ]

    timeout_per_skenario = max(10, timeout_user // len(skenario_list))
    berhasil = False

    with st.spinner("Sedang memproses dan mengoptimasi jadwal..."):
        for i, skenario in enumerate(skenario_list, start=1):
            st.write(
                f"⏳ **Mencoba {skenario['desc']}** (Timeout: {timeout_per_skenario}s)..."
            )

            solver = SchedulerSolver(scheduler_data)
            is_success = solver.run_solver(
                timeout_seconds=timeout_per_skenario,
                max_jam_mgmp_nongtt=skenario["max_mgmp"],
                max_jp_per_hari=skenario["max_jp"],
            )

            if is_success:
                st.success(
                    f"🎉 **BERHASIL!** Solusi ditemukan pada Skenario {i}."
                )
                df_hasil = solver.extract_results()
                df_laporan = solver.generate_teacher_report(df_hasil)

                # Format Gabungan Guru & Mapel untuk Tampilan Matriks
                df_hasil["Guru_Mapel"] = (
                    df_hasil["ID_Guru"].astype(str)
                    + " ("
                    + df_hasil["ID_Mapel"].astype(str)
                    + ")"
                )

                pivot_rombel = df_hasil.pivot_table(
                    index=["Hari", "Jam_Ke"],
                    columns="ID_Rombel",
                    values="Guru_Mapel",
                    aggfunc=lambda x: "/".join(x),
                    observed=False,
                ).fillna("-")

                # Tabs Tampilan
                tab1, tab2, tab3 = st.tabs(
                    [
                        "📊 Matriks Jadwal Rombel",
                        "📝 Detail Tabel",
                        "👨‍🏫 Rekap Guru",
                    ]
                )

                with tab1:
                    st.dataframe(pivot_rombel, use_container_width=True)

                with tab2:
                    df_show = df_hasil.drop(
                        columns=["Guru_Mapel"], errors="ignore"
                    )
                    st.dataframe(df_show, use_container_width=True)

                with tab3:
                    st.dataframe(df_laporan, use_container_width=True)

                # Download File Excel Result
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df_hasil.drop(
                        columns=["Guru_Mapel"], errors="ignore"
                    ).to_excel(
                        writer, sheet_name="Jadwal_Detail", index=False
                    )
                    pivot_rombel.to_excel(writer, sheet_name="Matriks_Kelas")
                    df_laporan.to_excel(
                        writer, sheet_name="Rekap_Beban_Guru", index=False
                    )

                st.download_button(
                    label="📥 Download Hasil Jadwal Lengkap (.xlsx)",
                    data=output.getvalue(),
                    file_name="Hasil_Jadwal_Pelajaran.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                berhasil = True
                break

    if not berhasil:
        st.error(
            "❌ **Gagal menemukan kombinasi.** Cobalah untuk menaikkan nilai Timeout di sidebar atau periksa ketersediaan jam mengajar di Excel."
        )
