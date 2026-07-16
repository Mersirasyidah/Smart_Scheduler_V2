# database.py
import os
import pandas as pd
import streamlit as st

DATABASE = "data/database_scheduler.xlsx"

def load_database():
    if not os.path.exists(DATABASE):
        st.error(f"❌ File database tidak ditemukan di lokasi:\n{DATABASE}")
        st.stop()
    try:
        excel = pd.ExcelFile(DATABASE, engine="openpyxl")
        data = {}
        for sheet in excel.sheet_names:
            data[sheet] = pd.read_excel(DATABASE, sheet_name=sheet, engine="openpyxl")
        return data
    except Exception as e:
        st.error("❌ Gagal membaca file Excel. Pastikan file tidak sedang dibuka di Excel/WPS.")
        st.error(str(e))
        st.stop()
