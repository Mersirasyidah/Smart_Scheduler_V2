# ==========================================================
# pages/7_🤖_AI_Scheduler.py
# Smart Scheduler V2
# ==========================================================

import streamlit as st
import pandas as pd
import os
import sys


# ==========================================================
# FIX IMPORT PATH
# Agar scheduler.py dan database.py terbaca
# ==========================================================

ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ==========================================================
# IMPORT MODULE PROJECT
# ==========================================================

try:

    from database import load_database
    from scheduler import Scheduler


except ModuleNotFoundError as e:

    st.error(
        "❌ Modul program tidak ditemukan."
    )

    st.write(
        "Folder project yang dibaca:"
    )

    st.code(ROOT_DIR)


    st.write(
        "Isi folder project:"
    )

    st.write(
        os.listdir(ROOT_DIR)
    )


    st.exception(e)

    st.stop()



# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title="AI Scheduler",
    page_icon="🤖",
    layout="wide"
)


# ==========================================================
# HEADER
# ==========================================================

st.title(
    "🤖 AI Scheduler V2"
)

st.caption(
    "Smart Scheduler V2 - AI Timetable Generator"
)

st.divider()



# ==========================================================
# LOAD DATABASE EXCEL
# ==========================================================

try:

    db = load_database()


except Exception as e:

    st.error(
        "Database gagal dibaca."
    )

    st.exception(e)

    st.stop()



# ==========================================================
# VALIDASI TABLE
# ==========================================================

required_tables = [

    "Guru",
    "Guru_Mengajar",
    "Rombel",
    "Mapel",
    "Hari_Jam"

]


missing = [

    t for t in required_tables
    if t not in db

]


if missing:

    st.error(
        "Tabel berikut belum tersedia: "
        + ", ".join(missing)
    )

    st.stop()



# Ambil tabel

guru = db["Guru"]

mengajar = db["Guru_Mengajar"]

rombel = db["Rombel"]

mapel = db["Mapel"]

hari_jam = db["Hari_Jam"]



# ==========================================================
# DASHBOARD
# ==========================================================

st.subheader(
    "📊 Statistik Database"
)


c1,c2,c3,c4,c5 = st.columns(5)


c1.metric(
    "Guru",
    len(guru)
)


c2.metric(
    "Mapel",
    len(mapel)
)


c3.metric(
    "Rombel",
    len(rombel)
)


c4.metric(
    "Mengajar",
    len(mengajar)
)


c5.metric(
    "Hari/Jam",
    len(hari_jam)
)



st.divider()



# ==========================================================
# PREVIEW DATA
# ==========================================================

with st.expander(
    "📂 Preview Database"
):


    tab1,tab2,tab3,tab4,tab5 = st.tabs(
        [
            "Guru",
            "Guru Mengajar",
            "Rombel",
            "Mapel",
            "Hari_Jam"
        ]
    )


    with tab1:

        st.dataframe(
            guru,
            use_container_width=True
        )


    with tab2:

        st.dataframe(
            mengajar,
            use_container_width=True
        )


    with tab3:

        st.dataframe(
            rombel,
            use_container_width=True
        )


    with tab4:

        st.dataframe(
            mapel,
            use_container_width=True
        )


    with tab5:

        st.dataframe(
            hari_jam,
            use_container_width=True
        )



st.divider()



# ==========================================================
# SESSION STATE
# ==========================================================

if "jadwal" not in st.session_state:

    st.session_state.jadwal = pd.DataFrame()



if "scheduler" not in st.session_state:

    st.session_state.scheduler = None



# ==========================================================
# BUTTON GENERATE
# ==========================================================

generate = st.button(

    "🚀 Generate Jadwal",

    type="primary",

    use_container_width=True

)



# ==========================================================
# RUN AI SOLVER
# ==========================================================

if generate:


    st.subheader(
        "🤖 AI Scheduler Progress"
    )


    progress = st.progress(0)

    status = st.empty()



    try:


        # ----------------------------------
        # INIT ENGINE
        # ----------------------------------

        status.info(
            "Membuat Scheduler Engine..."
        )


        scheduler = Scheduler(db)


        st.session_state.scheduler = scheduler


        progress.progress(15)



        # ----------------------------------
        # PREPARE ENGINE
        # ----------------------------------

        status.info(
            "Mempersiapkan slot pembelajaran..."
        )


        scheduler.prepare_engine()


        progress.progress(35)



        # ----------------------------------
        # AUDIT KAPASITAS
        # ----------------------------------

        total_jp = int(
            scheduler.mengajar[
                scheduler.col_jp
            ].sum()
        )


        total_slot = len(
            scheduler.slot
        )


        total_kelas = len(
            scheduler.rombel
        )


        kapasitas = (
            total_slot *
            total_kelas
        )



        st.info(
f"""
### 📋 Audit Kapasitas

Total JP kebutuhan:
**{total_jp} JP**

Jumlah kelas:
**{total_kelas}**

Jumlah slot:
**{total_slot}**

Kapasitas maksimal:
**{kapasitas} JP**
"""
        )



        if total_jp > kapasitas:


            st.error(
                f"""
🚨 Kapasitas tidak mencukupi.

Kebutuhan:
{total_jp} JP

Kapasitas:
{kapasitas} JP

Kurangi:
{total_jp-kapasitas} JP
"""
            )


            progress.progress(100)

            st.stop()



        progress.progress(50)



        # ----------------------------------
        # SOLVER
        # ----------------------------------

        status.info(
            "Menjalankan AI Solver CP-SAT..."
        )


        sukses = scheduler.solve(
            timeout_seconds=60
        )


        progress.progress(90)



        if sukses:


            st.session_state.jadwal = (
                scheduler.df_hasil
            )


            progress.progress(100)


            status.success(
                "AI berhasil membuat jadwal"
            )


            st.success(
                "🎉 Jadwal berhasil dibuat!"
            )


        else:


            progress.progress(100)


            st.error(
                "AI tidak menemukan solusi."
            )




    except Exception as e:


        st.error(
            "Terjadi error saat generate jadwal."
        )


        st.exception(e)



# ==========================================================
# OUTPUT
# ==========================================================

if not st.session_state.jadwal.empty:


    st.subheader(
        "🗓️ Hasil Jadwal Generasi AI"
    )


    st.dataframe(
        st.session_state.jadwal,
        use_container_width=True
    )



    try:


        excel_data = (
            st.session_state.scheduler.export()
        )


        if excel_data:


            st.download_button(

                label=
                "📥 Unduh Jadwal Excel",

                data=excel_data,

                file_name=
                "Jadwal_Sekolah_AI_V2.xlsx",

                mime=
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

                use_container_width=True

            )



    except Exception as e:


        st.warning(
            "Export Excel gagal."
        )


        st.exception(e)
