import pandas as pd
import streamlit as st

def load_excel_sheets(uploaded_file):
    excel_file = pd.ExcelFile(uploaded_file)
    sheet_names = excel_file.sheet_names
    
    # Fungsi pembantu untuk mencari sheet tanpa memedulikan spasi & huruf besar/kecil
    def get_sheet_df(target_name):
        normalized_target = target_name.lower().replace("_", "").replace(" ", "")
        for sheet in sheet_names:
            normalized_sheet = sheet.lower().replace("_", "").replace(" ", "")
            if normalized_sheet == normalized_target:
                return pd.read_excel(excel_file, sheet_name=sheet)
        return None

    # Membaca masing-masing sheet secara fleksibel
    guru_df = get_sheet_df("Guru")
    rombel_df = get_sheet_df("Rombel")
    mengajar_df = get_sheet_df("Guru_Mengajar")  # Toleran ke "Guru Mengajar", "guru_mengajar", dll.
    mapel_df = get_sheet_df("Mapel")
    slot_df = get_sheet_df("Slot")

    if mengajar_df is None:
        st.error("❌ Sheet 'Guru_Mengajar' atau 'Guru Mengajar' tidak ditemukan di file Excel!")
        return None, None, None, None, None

    return guru_df, rombel_df, mengajar_df, mapel_df, slot_df
