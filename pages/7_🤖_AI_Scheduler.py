import io
import pandas as pd
import streamlit as st
from scheduler_engine import Scheduler

st.set_page_config(page_title="AI Scheduler", page_icon="🤖", layout="wide")

st.title("🤖 AI Scheduler")
st.markdown(
    """
Gunakan modul AI ini untuk membuat jadwal pelajaran otomatis berdasarkan aturan constraint 
(MGMP Guru Reguler vs GTT, Batas JP Harian, Jam PJOK, dan Pembagian Jam Berurutan).
"""
)

st.sidebar.header("⚙️ Pengaturan Solver")
timeout_seconds = st.sidebar.number_input(
    "Waktu Pencarian Maksimal (Detik)",
    min_value=30,
    max_value=600,
    value=120,
    step=30,
    help="Semakin lama waktu pencarian, semakin tinggi peluang solver menemukan kombinasi yang optimal.",
)

# Section Upload File
st.subheader("1. Unggah File Master Excel")
uploaded_file = st.file_uploader(
    "Pilih file Excel jadwal (harus memiliki sheet: Guru, Rombel, Mengajar, Mapel, Slot)",
    type=["xlsx"],
)

if uploaded_file:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        sheet_names = excel_file.sheet_names

        # Validasi sheet wajib
        required_sheets = ["Guru", "Rombel", "Mengajar", "Mapel", "Slot"]
        missing_sheets = [
            s for s in required_sheets if s not in sheet_names
        ]

        if missing_sheets:
            st.error(
                f"❌ Sheet berikut tidak ditemukan dalam file Excel: {', '.join(missing_sheets)}"
            )
        else:
            # Load Dataframe
            guru_df = pd.read_excel(excel_file, "Guru")
            rombel_df = pd.read_excel(excel_file, "Rombel")
            mengajar_df = pd.read_excel(excel_file, "Mengajar")
            mapel_df = pd.read_excel(excel_file, "Mapel")
            slot_df = pd.read_excel(excel_file, "Slot")

            st.success("✅ Seluruh sheet master berhasil dibaca!")

            # Preview Ringkasan Data
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Guru", len(guru_df))
            col2.metric("Total Rombel", len(rombel_df))
            col3.metric("Total Tugas Mengajar", len(mengajar_df))
            col4.metric("Total Slot Waktu", len(slot_df))

            st.markdown("---")
            st.subheader("2. Eksekusi AI Solver")

            if st.button("🚀 Jalankan Penjadwalan Otomatis", type="primary"):
                status_box = st.empty()
                progress_bar = st.progress(0)

                def update_status_callback(pesan):
                    status_box.info(f"⏳ **Proses:** {pesan}")

                # Inisialisasi Engine Scheduler
                scheduler = Scheduler(
                    guru_df, rombel_df, mengajar_df, mapel_df, slot_df
                )

                # Jalankan solver dengan strategi fallback bertahap
                success, df_hasil, df_laporan_guru, desc_skenario = (
                    scheduler.solve_with_fallback(
                        timeout_total=timeout_seconds,
                        progress_callback=update_status_callback,
                    )
                )

                progress_bar.progress(100)

                if success:
                    status_box.success(
                        f"🎉 **Penjadwalan Berhasil!** ({desc_skenario})"
                    )

                    st.markdown("---")
                    st.subheader("📊 Hasil Penjadwalan")

                    tab1, tab2, tab3 = st.tabs(
                        [
                            "📅 Matriks Jadwal",
                            "👨‍🏫 Laporan Guru",
                            "📥 Download Excel",
                        ]
                    )

                    with tab1:
                        st.markdown("##### Tabel Hasil Plotting Jam Belajar")
                        st.dataframe(df_hasil, use_container_width=True)

                    with tab2:
                        st.markdown(
                            "##### Laporan Distribusi Mengajar Per Guru"
                        )
                        st.dataframe(df_laporan_guru, use_container_width=True)

                    with tab3:
                        st.markdown("##### Unduh Data Hasil Penjadwalan")

                        # Konversi Hasil ke Excel Stream
                        output = io.BytesIO()
                        with pd.ExcelWriter(
                            output, engine="openpyxl"
                        ) as writer:
                            df_hasil.to_excel(
                                writer, sheet_name="Jadwal_Master", index=False
                            )
                            df_laporan_guru.to_excel(
                                writer, sheet_name="Laporan_Guru", index=False
                            )

                        excel_data = output.getvalue()

                        st.download_button(
                            label="📥 Download File Excel Hasil Jadwal",
                            data=excel_data,
                            file_name="Hasil_Penjadwalan_AI.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                else:
                    status_box.error(
                        "❌ **Solver Gagal Menemukan Solusi.**\n\n"
                        "**Saran Perbaikan:**\n"
                        "1. Longgarkan ketersediaan jam di sheet `Slot`.\n"
                        "2. Periksa apakah ada guru yang bentrok jam MGMP-nya pada hari yang sama.\n"
                        "3. Naikkan nilai **Waktu Pencarian Maksimal** pada sidebar kiri."
                    )

    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca file: {str(e)}")
else:
    st.info("💡 Silakan unggah file Excel Anda untuk memulai.")
