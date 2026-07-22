import io
import pandas as pd
import streamlit as st
from scheduler_engine import Scheduler

st.set_page_config(
    page_title="AI Scheduler", page_icon="🤖", layout="wide"
)

st.title("🤖 AI Scheduler")
st.markdown(
    """
Modul AI Penjadwalan Otomatis. Hasil ekspor akan otomatis membentuk **sheet master (`Jadwal_Semua_Kelas`)** 
serta **sheet terpisah per kelas (`Kelas_7A`, `Kelas_7B`, dsb.)** sesuai format template Anda.
"""
)

st.sidebar.header("⚙️ Pengaturan Solver")
timeout_seconds = st.sidebar.number_input(
    "Waktu Pencarian Maksimal (Detik)",
    min_value=30,
    max_value=600,
    value=180,
    step=30,
    help="Semakin lama waktu pencarian, semakin tinggi peluang solver menemukan kombinasi optimal.",
)

# 1. Section Upload File
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

            # Hitung Slot Pembelajaran
            col_jenis = next(
                (
                    c
                    for c in slot_df.columns
                    if str(c).strip().lower() == "jenis"
                ),
                None,
            )
            if col_jenis:
                slot_pembelajaran_count = len(
                    slot_df[
                        slot_df[col_jenis]
                        .astype(str)
                        .str.strip()
                        .str.upper()
                        == "PEMBELAJARAN"
                    ]
                )
            else:
                slot_pembelajaran_count = len(slot_df)

            # Preview Ringkasan Data
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Guru", len(guru_df))
            col2.metric("Total Rombel", len(rombel_df))
            col3.metric("Total Tugas Mengajar", len(mengajar_df))
            col4.metric("Total Slot Pembelajaran", slot_pembelajaran_count)

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

                if success and not df_hasil.empty:
                    status_box.success(
                        f"🎉 **Penjadwalan Berhasil!** ({desc_skenario})"
                    )

                    # --- MAPPING NAMA GURU & NAMA MAPEL LENGKAP ---
                    col_guru_id = next(
                        (
                            c
                            for c in guru_df.columns
                            if "id" in c.lower() and "guru" in c.lower()
                        ),
                        guru_df.columns[0],
                    )
                    col_guru_nama = next(
                        (c for c in guru_df.columns if "nama" in c.lower()),
                        col_guru_id,
                    )
                    guru_map = dict(
                        zip(
                            guru_df[col_guru_id].astype(str).str.strip(),
                            guru_df[col_guru_nama].astype(str).str.strip(),
                        )
                    )

                    col_mapel_id = next(
                        (
                            c
                            for c in mapel_df.columns
                            if "id" in c.lower() and "mapel" in c.lower()
                        ),
                        mapel_df.columns[0],
                    )
                    col_mapel_nama = next(
                        (c for c in mapel_df.columns if "nama" in c.lower()),
                        col_mapel_id,
                    )
                    mapel_map = dict(
                        zip(
                            mapel_df[col_mapel_id].astype(str).str.strip(),
                            mapel_df[col_mapel_nama].astype(str).str.strip(),
                        )
                    )

                    # Buat DataFrame Utama yang Rapi
                    df_master = df_hasil.copy()
                    df_master["Nama Guru"] = (
                        df_master["ID_Guru"]
                        .astype(str)
                        .str.strip()
                        .map(guru_map)
                        .fillna(df_master["ID_Guru"])
                    )
                    df_master["Mata Pelajaran"] = (
                        df_master["ID_Mapel"]
                        .astype(str)
                        .str.strip()
                        .map(mapel_map)
                        .fillna(df_master["ID_Mapel"])
                    )

                    # Reorder & rename kolom master sesuai template "Jadwal_Semua_Kelas"
                    df_master_export = df_master[
                        [
                            "Hari",
                            "Jam_Ke",
                            "ID_Rombel",
                            "Nama Guru",
                            "Mata Pelajaran",
                        ]
                    ].rename(
                        columns={
                            "Jam_Ke": "Jam Ke",
                            "ID_Rombel": "Kelas / Rombel",
                        }
                    )

                    st.markdown("---")
                    st.subheader("📊 Hasil Penjadwalan")

                    tab1, tab2, tab3 = st.tabs(
                        [
                            "📋 Jadwal Semua Kelas",
                            "🏫 Pratinjau Per Kelas",
                            "📥 Download Excel Multi-Sheet",
                        ]
                    )

                    # TAB 1: Master Semua Kelas
                    with tab1:
                        st.markdown("##### Tabel Master: `Jadwal_Semua_Kelas`")
                        st.dataframe(df_master_export, use_container_width=True)

                    # TAB 2: Grid Pratinjau Per Kelas
                    with tab2:
                        list_rombel = sorted(
                            df_master["ID_Rombel"].unique().tolist()
                        )
                        selected_kelas = st.selectbox(
                            "Pilih Kelas / Rombel:", list_rombel
                        )

                        df_kelas = df_master[
                            df_master["ID_Rombel"] == selected_kelas
                        ]
                        pivot_kelas = df_kelas.pivot_table(
                            index="Jam_Ke",
                            columns="Hari",
                            values="Nama Guru",
                            aggfunc="first",
                        ).fillna("-")

                        st.markdown(f"##### Matriks Jadwal **Kelas {selected_kelas}**")
                        st.dataframe(pivot_kelas, use_container_width=True)

                    # TAB 3: Download File Excel dengan Format Persis 'Jadwal baru.xlsx'
                    with tab3:
                        st.markdown(
                            "##### Unduh File Excel dengan Sheet Terpisah Per Kelas"
                        )

                        output = io.BytesIO()
                        with pd.ExcelWriter(
                            output, engine="openpyxl"
                        ) as writer:
                            # 1. Sheet Pertama: Jadwal_Semua_Kelas
                            df_master_export.to_excel(
                                writer,
                                sheet_name="Jadwal_Semua_Kelas",
                                index=False,
                            )

                            # 2. Sheet Berikutnya: Per Kelas (Kelas_7A, Kelas_7B, dst.)
                            list_rombel = sorted(
                                df_master["ID_Rombel"].unique().tolist()
                            )
                            for r in list_rombel:
                                df_r = df_master[df_master["ID_Rombel"] == r]
                                pivot_r = df_r.pivot_table(
                                    index="Jam_Ke",
                                    columns="Hari",
                                    values="Nama Guru",
                                    aggfunc="first",
                                ).reset_index()

                                # Simpan ke Sheet Kelas_XX
                                sheet_title = f"Kelas_{r}"
                                pivot_r.to_excel(
                                    writer,
                                    sheet_name=sheet_title,
                                    index=False,
                                )

                            # 3. Sheet Laporan Guru
                            df_laporan_guru.to_excel(
                                writer,
                                sheet_name="Laporan_Beban_Guru",
                                index=False,
                            )

                        excel_bytes = output.getvalue()

                        st.download_button(
                            label="📥 Download Excel (Format Multi-Sheet Per Kelas)",
                            data=excel_bytes,
                            file_name="Jadwal_Pelajaran_Lengkap.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )

                else:
                    status_box.error(
                        "❌ **Solver Gagal Menemukan Solusi.**\n\n"
                        "**Saran Perbaikan:**\n"
                        "1. Longgarkan ketersediaan jam di sheet `Slot`.\n"
                        "2. Periksa apakah ada guru mapel sama yang bentrok jam MGMP-nya pada hari yang sama.\n"
                        "3. Naikkan nilai **Waktu Pencarian Maksimal** pada sidebar kiri."
                    )

    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca file: {str(e)}")
else:
    st.info("💡 Silakan unggah file Excel Anda untuk memulai.")
