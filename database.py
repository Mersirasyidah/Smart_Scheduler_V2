import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Mengakomodasi file nama database_scheduler.xlsx
DATABASE = os.path.join(BASE_DIR, "data", "database_scheduler.xlsx")


def load_database():
    """Membaca seluruh sheet dari file Excel master."""
    if not os.path.exists(DATABASE):
        return {}

    try:
        excel = pd.ExcelFile(DATABASE, engine="openpyxl")
        data = {}
        for sheet in excel.sheet_names:
            clean_name = str(sheet).strip()
            data[clean_name] = pd.read_excel(
                DATABASE, sheet_name=sheet, engine="openpyxl"
            )
        return data
    except Exception as e:
        return {}


def get_all_data():
    """Mengambil semua sheet dengan pemetaan nama sheet & normalisasi nama kolom."""
    db = load_database()
    if not db:
        return None

    def find_sheet(possible_names):
        for name in db.keys():
            if name.lower().strip() in [p.lower() for p in possible_names]:
                df = db[name].copy()
                # Standarisasi nama kolom: ubah spasi menjadi underscore 'ID Guru' -> 'ID_Guru'
                df.columns = [
                    str(c).strip().replace(" ", "_") for c in df.columns
                ]
                return df
        return pd.DataFrame()

    guru = find_sheet(["Guru"])
    rombel = find_sheet(["Rombel", "Kelas"])
    mengajar = find_sheet(["Guru_Mengajar", "Mengajar"])
    mapel = find_sheet(["Mapel"])
    slot = find_sheet(["Hari_Jam", "Slot", "Jadwal_Slot"])

    # Pengecekan sheet penting
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
