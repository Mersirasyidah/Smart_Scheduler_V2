# scheduler_engine.py
import pandas as pd
from scheduler.solver import SchedulerSolver
from scheduler.exporter import ScheduleExporter

class Scheduler:
    def __init__(self, db):
        self.db = db
        self.guru = db["Guru"]
        self.mengajar = db["Guru_Mengajar"]
        self.rombel = db["Rombel"]
        self.mapel = db["Mapel"]
        self.hari_jam = db["Hari_Jam"]
        
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
        exporter = ScheduleExporter(self.df_hasil, self.db)
        return exporter.generate_excel()
