# ==========================================================
# pages/7_🤖_AI_Scheduler.py
# Smart Scheduler V2
# ==========================================================

import streamlit as st
import pandas as pd
import os
import sys


# ==========================================================
# ROOT PATH PROJECT
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
# IMPORT MODULE
# ==========================================================

try:

    from database import load_database

    # PERBAIKAN UTAMA
    from scheduler_engine import Scheduler


except Exception as e:

    st.error(
        "❌ Modul Scheduler tidak ditemukan."
    )

    st.write(
        "Folder project:"
    )

    st.code(ROOT_DIR)


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
# LOAD DATABASE
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
# CEK TABLE EXCEL
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
        "Tabel tidak ditemukan: "
        +
        ", ".join(missing)
    )

    st.stop()



guru = db["Guru"]

mengajar = db["Guru_Mengajar"]

rombel = db["Rombel"]

mapel = db["Mapel"]

hari_jam = db["Hari_Jam"]



# ==========================================================
# STATISTIK
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
    "Guru Mengajar",
    len(mengajar)
)


c5.metric(
    "Slot Hari/Jam",
    len(hari_jam)
)



st.divider()



# ==========================================================
# PREVIEW DATA
# ==========================================================

with st.expander(
    "📂 Preview Database"
):


    t1,t2,t3,t4,t5 = st.tabs(
        [
            "Guru",
            "Guru Mengajar",
            "Rombel",
            "Mapel",
            "Hari_Jam"
        ]
    )


    with t1:
        st.dataframe(
            guru,
            use_container_width=True
        )


    with t2:
        st.dataframe(
            mengajar,
            use_container_width=True
        )


    with t3:
        st.dataframe(
            rombel,
            use_container_width=True
        )


    with t4:
        st.dataframe(
            mapel,
            use_container_width=True
        )


    with t5:
        st.dataframe(
            hari_jam,
            use_container_width=True
        )



st.divider()



# ==========================================================
# SESSION
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
# GENERATE PROCESS
# ==========================================================

if generate:


    progress = st.progress(0)

    status = st.empty()


    try:


        status.info(
            "Membuat Scheduler Engine..."
        )


        scheduler = Scheduler(db)


        st.session_state.scheduler = scheduler


        progress.progress(20)



        status.info(
            "Menyiapkan data scheduler..."
        )


        scheduler.prepare_engine()


        progress.progress(40)



        # AUDIT KAPASITAS

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

Total JP:
**{total_jp}**

Total Kelas:
**{total_kelas}**

Total Slot:
**{total_slot}**

Kapasitas:
**{kapasitas} JP**
"""
        )



        if total_jp > kapasitas:


            st.error(
                "❌ JP melebihi kapasitas jadwal."
            )

            st.stop()



        progress.progress(60)



        status.info(
            "Menjalankan AI Solver CP-SAT..."
        )


        hasil = scheduler.solve(
            timeout_seconds=60
        )


        progress.progress(90)



        if hasil:


            st.session_state.jadwal = (
                scheduler.df_hasil
            )


            progress.progress(100)


            st.success(
                "🎉 Jadwal berhasil dibuat!"
            )


        else:

            st.error(
                "AI tidak menemukan solusi."
            )



    except Exception as e:


        st.error(
            "Error saat generate jadwal."
        )

        st.exception(e)




# ==========================================================
# HASIL JADWAL
# ==========================================================

if not st.session_state.jadwal.empty:


    st.subheader(
        "🗓️ Hasil Jadwal AI"
    )


    st.dataframe(
        st.session_state.jadwal,
        use_container_width=True
    )



    try:


        excel = (
            st.session_state.scheduler.export()
        )


        if excel:


            st.download_button(

                label="📥 Download Excel",

                data=excel,

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
