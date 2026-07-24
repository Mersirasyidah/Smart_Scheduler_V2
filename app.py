import io
import os
import pandas as pd
import streamlit as st
from database import get_all_data
from solver import SchedulerSolver

st.set_page_config(
    page_title="AI Scheduler Penjadwalan Sekolah", page_icon="🤖", layout="wide"
)

st.title("🤖 AI Scheduler - Generator Jadwal Otomatis")
st.caption(
    "Optimasi pembuatan jadwal KBM sekolah menggunakan Google OR-Tools CP-SAT Solver."
)


# Class Wrapper
class SchedulerData:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df


# ==========================================================
# MEKANISME AUTO-LOAD DATA MASTER (ANTI-LOCK)
# ==========================================================
st.sidebar.header("📁 Sumber Data Master")
uploaded_file = st.sidebar.file_uploader(
    "Upload File Excel Baru (Opsional)", type=["xlsx", "xls"]
)

scheduler_data = None

# 1. Prioritas Utama: Baca file yang diunggah pengguna
if uploaded_file is not None:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        sheets = [s.strip() for s in excel_file.sheet_names]

        guru_df = pd.read_excel(excel_file, "Guru")
        rombel_df = pd.read_excel(
            excel_file, "Rombel" if "Rombel" in sheets else "Kelas"
        )
        mengajar_df = pd.read_excel(
            excel_file, "Mengajar" if "Mengajar" in sheets else "Guru_Mengajar"
        )
        mapel_df = pd.read_excel(excel_file, "Mapel")
        slot_df = pd.read_excel(
            excel_file, "Slot" if "Slot" in sheets else "Hari_Jam"
        )

        scheduler_data = SchedulerData(
            guru_df, rombel_df, mengajar_df, mapel_df, slot_df
        )
        st.sidebar.success("✅ File Excel unggahan berhasil dibaca!")
    except Exception as e:
        st.sidebar.error(f"❌ Error membaca file upload: {e}")

# 2. Prioritas Kedua: Muat Otomatis dari data/database_scheduler.xlsx via database.py
if scheduler_data is None:
    data_dict = get_all_data()
    if data_dict:
        scheduler_data = SchedulerData(
            data_dict["guru"],
            data_dict["rombel"],
            data_dict["mengajar"],
            data_dict["mapel"],
            data_dict["slot"],
        )
        st.sidebar.info("ℹ️ Menggunakan database master lokal (data/).")

timeout_user = st.sidebar.slider(
    "Total Durasi Timeout Solver (Detik)", 30, 300, 120, 30
)

# ==========================================================
# GUARD CLAUSE AKHIR (HANYA MUNCUL JIKA KEDUA METHOD GAGAL)
# ==========================================================
if scheduler_data is None:
    st.error("⚠️ **Data Master Belum Siap!**")
    st.warning(
        "Sistem tidak menemukan database lokal di folder `data/database_scheduler.xlsx` "
        "dan belum ada file Excel yang diunggah.\n\n"
        "**Solusi:** Silakan upload file Excel yang berisi sheet `Guru`, `Rombel`, `Mengajar`, `Mapel`, dan `Slot` "
        "pada menu upload di sidebar kiri."
    )
    st.stop()

# ==========================================================
# EKSEKUSI SOLVER
# ==========================================================
st.success("🎉 Data Master Terdeteksi Lengkap & Siap Digunakan!")

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
