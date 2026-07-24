import pandas as pd
import os

EXCEL_PATH = os.path.join("data", "database_scheduler.xlsx")

class DatabaseManager:
    def __init__(self, file_path=EXCEL_PATH):
        self.file_path = file_path

    def load_all_data(self):
        """Membaca seluruh sheet dari database Excel."""
        xls = pd.ExcelFile(self.file_path)
        data = {
            "guru": pd.read_excel(xls, "Guru"),
            "mapel": pd.read_excel(xls, "Mapel"),
            "rombel": pd.read_excel(xls, "Rombel"),
            "guru_mengajar": pd.read_excel(xls, "Guru_Mengajar"),
            "hari_jam": pd.read_excel(xls, "Hari_Jam")
        }
        return data

    def get_time_slots(self):
        """Mengambil slot jam pelajaran efektif (bukan upacara/istirahat)."""
        df_jam = pd.read_excel(self.file_path, sheet_name="Hari_Jam")
        # Filter hanya slot jam pembelajaran (Jam != NaN)
        df_pembelajaran = df_jam[df_jam['Jam'].notna()].copy()
        df_pembelajaran['Jam'] = df_pembelajaran['Jam'].astype(int)
        return df_pembelajaran
