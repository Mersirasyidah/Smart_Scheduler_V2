import glob
import os
import pandas as pd


def get_database_path():
    """Mencari lokasi file database Excel secara fleksibel."""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Daftar opsi lokasi yang dicoba
    candidate_paths = [
        # Dalam folder data/
        os.path.join(BASE_DIR, "data", "database_scheduler.xlsx"),
        os.path.join(BASE_DIR, "data", "database_scheduler_2.xlsx"),
        # Di folder utama (sejajar app.py)
        os.path.join(BASE_DIR, "database_scheduler.xlsx"),
        os.path.join(BASE_DIR, "database_scheduler_2.xlsx"),
    ]

    # Cek kandidat path pasti
    for path in candidate_paths:
        if os.path.exists(path):
            return path

    # Jika tidak ketemu, cari file .xlsx apapun yang mengandung kata 'database' atau 'scheduler'
    search_patterns = [
        os.path.join(BASE_DIR, "data", "*.xlsx"),
        os.path.join(BASE_DIR, "*.xlsx"),
    ]

    for pattern in search_patterns:
        files = glob.glob(pattern)
        for f in files:
            filename = os.path.basename(f).lower()
            if "scheduler" in filename or "database" in filename or "jadwal" in filename:
                return f

    return None


def load_database():
    """Membaca seluruh sheet dari file Excel yang ditemukan."""
    db_path = get_database_path()
    if not db_path or not os.path.exists(db_path):
        return {}

    try:
        excel = pd.ExcelFile(db_path, engine="openpyxl")
        data = {}
        for sheet in excel.sheet_names:
            clean_name = str(sheet).strip()
            data[clean_name] = pd.read_excel(
                db_path, sheet_name=sheet, engine="openpyxl"
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
                # Standarisasi kolom: ubah 'ID Guru' menjadi 'ID_Guru'
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
