# scheduler_engine.py
import pandas as pd
from scheduler_core.solver import SchedulerSolver
from scheduler_core.exporter import ScheduleExporter

class Scheduler:
    def __init__(self, db):
        self.db = db
        
        # 1. Normalisasi & Penyesuaian Kolom GURU
        self.guru = db["Guru"].copy()
        self.guru.columns = [c.replace(" ", "_") for c in self.guru.columns]
        
        # 2. Normalisasi & Penyesuaian Kolom ROMBEL/KELAS
        self.rombel = db["Rombel"].copy()
        self.rombel.columns = [c.replace(" ", "_") for c in self.rombel.columns]
        if "Kelas" in self.rombel.columns:
            self.rombel["ID_Rombel"] = self.rombel["Kelas"]
            self.rombel["Nama_Rombel"] = self.rombel["Kelas"]
        
        # 3. Normalisasi & Penyesuaian Kolom GURU_MENGAJAR
        self.mengajar = db["Guru_Mengajar"].copy()
        self.mengajar.columns = [c.replace(" ", "_") for c in self.mengajar.columns]
        if "Kelas" in self.mengajar.columns:
            self.mengajar["ID_Rombel"] = self.mengajar["Kelas"]

        # 4. Normalisasi Kolom MAPEL
        self.mapel = db["Mapel"].copy()
        self.mapel.columns = [c.replace(" ", "_") for c in self.mapel.columns]
        if "ID_Mapel" not in self.mapel.columns and "Mapel" in self.mapel.columns:
            self.mapel["ID_Mapel"] = self.mapel["Mapel"]
            self.mapel["Nama_Mapel"] = self.mapel["Mapel"]
        if "ID_Mapel" not in self.mengajar.columns and "Mapel" in self.mengajar.columns:
            self.mengajar["ID_Mapel"] = self.mengajar["Mapel"]
        
        # 5. Normalisasi Kolom HARI_JAM
        self.hari_jam = db["Hari_Jam"].copy()
        self.hari_jam.columns = [c.replace(" ", "_") for c in self.hari_jam.columns]
        if "Jam" in self.hari_jam.columns:
            self.hari_jam["Jam_Ke"] = self.hari_jam["Jam"]
        
        self.col_jp = "JP"
        self.solver_engine = None
        self.df_hasil = pd.DataFrame()

    def prepare_engine(self):
        # Saring slot yang aktif / hanya bertipe pembelajaran
        self.slot = self.hari_jam[self.hari_jam["Jenis"].str.lower() == "pembelajaran"].copy()
        self.solver_engine = SchedulerSolver(self)

    def solve(self, timeout_seconds=60.0):
        if not self.solver_engine:
            self.prepare_engine()
        
        sukses = self.solver_engine.run_solver(timeout_seconds)
        if sukses:
            self.df_hasil = self.solver_engine.extract_results()
        return sukses

    def export(self):
        if self.df_hasil.empty:
            return None
        
        # DENORMALISASI KHUSUS UNTUK EXPORTER:
        # Kembalikan semua nama kolom ke format asli dengan spasi ("Jam Ke", "ID Guru", dll.)
        # agar sesuai dengan ekspektasi exporter.py bawaan Anda.
        df_export = self.df_hasil.copy()
        
        rename_map = {
            "ID_Guru": "ID Guru",
            "Nama_Guru": "Nama Guru",
            "ID_Rombel": "Kelas",
            "ID_Mapel": "Mapel",
            "Jam_Ke": "Jam Ke"
        }
        
        # Ganti nama kolom yang ada di df_export jika kolom tersebut eksis
        df_export = df_export.rename(columns={k: v for k, v in rename_map.items() if k in df_export.columns})
        
        # Tambahkan kolom "Jam Ke" jika exporter membutuhkannya secara spesifik dari "Jam"
        if "Jam Ke" not in df_export.columns and "Jam" in df_export.columns:
            df_export["Jam Ke"] = df_export["Jam"]
            
        exporter = ScheduleExporter(df_export, self.db)
        return exporter.generate_excel()
