import io
import pandas as pd
from solver import SchedulerSolver
import streamlit as st

st.set_page_config(
    page_title="Sistem Penjadwalan Sekolah", page_icon="📅", layout="wide"
)

st.title("📅 Auto-Scheduler Penjadwalan Sekolah")
st.markdown(
    "Aplikasi penjadwalan otomatis menggunakan **Google OR-Tools CP-SAT Solver**."
)


# Class Mockup Data Wrapper (Menyesuaikan input Streamlit)
class SchedulerData:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df


# Sidebar Input / Upload Data
st.sidebar.header("📁 Unggah File Data Excel")
uploaded_file = st.sidebar.file_uploader(
    "Upload File Excel Master", type=["xlsx", "xls"]
)

timeout_user = st.sidebar.slider(
    "Durasi Timeout Solver (Detik)", 30, 300, 120, 30
)

if uploaded_file:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        guru_df = pd.read_excel(excel_file, "Guru")
        rombel_df = pd.read_excel(excel_file, "Rombel")
        mengajar_df = pd.read_excel(excel_file, "Mengajar")
        mapel_df = pd.read_excel(excel_file, "Mapel")
        slot_df = pd.read_excel(excel_file, "Slot")

        scheduler_data = SchedulerData(
            guru_df, rombel_df, mengajar_df, mapel_df, slot_df
        )
        st.success("✅ Seluruh sheet Excel berhasil dibaca.")

        if st.button("🚀 Process Penjadwalan Otomatis", type="primary"):
            st.info("Memulai proses penjadwalan bertahap...")

            # DUA SKENARIO UTAMA BERTINGKAT
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

            for i, skenario in enumerate(skenario_list, start=1):
                st.write(
                    f"⏳ **Mencoba {skenario['desc']}** (Timeout: {timeout_per_skenario}d)..."
                )

                solver = SchedulerSolver(scheduler_data)
                is_success = solver.run_solver(
                    timeout_seconds=timeout_per_skenario,
                    max_jam_mgmp_nongtt=skenario["max_mgmp"],
                    max_jp_per_hari=skenario["max_jp"],
                )

                if is_success:
                    st.success(f"🎉 **BERHASIL!** Solusi ditemukan di Skenario {i}.")
                    df_hasil = solver.extract_results()
                    df_laporan = solver.generate_teacher_report(df_hasil)

                    # TAMPILKAN HASIL
                    tab1, tab2, tab3 = st.tabs(
                        [
                            "📊 Matriks Jadwal Rombel",
                            "📝 Detail Tabel",
                            "👨‍🏫 Rekap Guru",
                        ]
                    )

                    with tab1:
                        pivot_rombel = df_hasil.pivot_table(
                            index=["Hari", "Jam_Ke"],
                            columns="ID_Rombel",
                            values="ID_Guru",
                            aggfunc=lambda x: "/".join(x),
                        ).fillna("-")
                        st.dataframe(pivot_rombel, use_container_width=True)

                    with tab2:
                        st.dataframe(df_hasil, use_container_width=True)

                    with tab3:
                        st.dataframe(df_laporan, use_container_width=True)

                    # TOMBOL DOWNLOAD EXCEL
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df_hasil.to_excel(
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

    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca file: {e}")
else:
    st.info("Silakan unggah file Excel data master di sidebar kiri untuk memulai.")
