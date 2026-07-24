import os
import pandas as pd
import streamlit as st

# Path absolut agar tidak nyasar
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "data", "database_scheduler.xlsx")


def load_database():
    """Membaca seluruh sheet dari file Excel master."""
    if not os.path.exists(DATABASE):
        return {}

    try:
        excel = pd.ExcelFile(DATABASE, engine="openpyxl")
        data = {}
        for sheet in excel.sheet_names:
            # Bersihkan nama sheet dari spasi liar
            clean_name = str(sheet).strip()
            data[clean_name] = pd.read_excel(
                DATABASE, sheet_name=sheet, engine="openpyxl"
            )
        return data
    except Exception as e:
        st.error(f"Error membaca database: {e}")
        return {}


def get_all_data():
    """Mengambil semua sheet sekaligus dengan pencarian nama fleksibel."""
    db = load_database()
    if not db:
        return None

    # Fungsi pencari sheet (case-insensitive & toleran spasi)
    def find_sheet(possible_names):
        for name in db.keys():
            if name.lower().strip() in [p.lower() for p in possible_names]:
                return db[name]
        return pd.DataFrame()

    guru = find_sheet(["Guru"])
    rombel = find_sheet(["Rombel", "Kelas"])
    mengajar = find_sheet(["Mengajar", "Guru_Mengajar"])
    mapel = find_sheet(["Mapel"])
    slot = find_sheet(["Slot", "Hari_Jam", "Jadwal_Slot"])

    # Validasi jika ada sheet utama yang kosong
    if guru.empty or mengajar.empty or slot.empty:
        return None

    return {
        "guru": guru,
        "rombel": rombel,
        "mengajar": mengajar,
        "mapel": mapel,
        "slot": slot,
    }


def get_guru():
    data = get_all_data()
    return data["guru"] if data else pd.DataFrame()


def get_rombel():
    data = get_all_data()
    return data["rombel"] if data else pd.DataFrame()


def get_mengajar():
    data = get_all_data()
    return data["mengajar"] if data else pd.DataFrame()


def get_mapel():
    data = get_all_data()
    return data["mapel"] if data else pd.DataFrame()


def get_slot():
    data = get_all_data()
    return data["slot"] if data else pd.DataFrame()
