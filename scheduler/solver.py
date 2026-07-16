# scheduler/solver.py
import time
import pandas as pd
from ortools.sat.python import cp_model
from .constraints import ConstraintBuilder

class SchedulerSolver:
    def __init__(self, scheduler_parent):
        self.p = scheduler_parent
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        
        # Referensi Dataframe
        self.df_guru_ref = self.p.guru
        self.df_guru = self.p.guru["Nama Guru"].unique()
        self.df_mengajar = self.p.mengajar
        self.df_rombel = self.p.rombel["Kelas"].unique()
        self.df_slot = self.p.slot
        
        # Index List
        self.idx_mengajar = self.df_mengajar.index.tolist()
        self.idx_slot = self.df_slot.index.tolist()
        self.idx_kelas = list(self.df_rombel)
        
        # Variabel Keputusan CP-SAT: vars[(m_idx, t_idx)]
        self.vars = {}
        for m_idx in self.idx_mengajar:
            for t_idx in self.idx_slot:
                self.vars[(m_idx, t_idx)] = self.model.NewBoolVar(f'x_m{m_idx}_t{t_idx}')
                
    def run_solver(self, timeout_seconds=60.0):
        # Bangun Constraints
        builder = ConstraintBuilder(self)
        builder.apply_all()
        
        # Konfigurasi Solver
        self.solver.parameters.max_time_in_seconds = float(timeout_seconds)
        self.solver.parameters.log_search_progress = True
        
        status = self.solver.Solve(self.model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            return True
        return False

    def extract_results(self):
        """Mengonversi variabel biner hasil optimasi menjadi format dataframe jadwal"""
        hasil = []
        for m_idx, row_m in self.df_mengajar.iterrows():
            for t_idx, row_t in self.df_slot.iterrows():
                if self.solver.Value(self.vars[(m_idx, t_idx)]) == 1:
                    hasil.append({
                        "Hari": row_t["Hari"],
                        "Jam": row_t["Jam"],
                        "Mulai": row_t["Mulai"],
                        "Selesai": row_t["Selesai"],
                        "Kelas": row_m["Kelas"],
                        "Nama Guru": row_m["Nama Guru"],
                        "Mata Pelajaran": row_m["Mapel"]
                    })
                    
        df_hasil = pd.DataFrame(hasil)
        if not df_hasil.empty:
            hari_order = {"Senin": 1, "Selasa": 2, "Rabu": 3, "Kamis": 4, "Jumat": 5}
            df_hasil["Hari_Order"] = df_hasil["Hari"].map(hari_order)
            df_hasil = df_hasil.sort_values(by=["Hari_Order", "Jam", "Kelas"]).drop(columns=["Hari_Order"])
        return df_hasil
