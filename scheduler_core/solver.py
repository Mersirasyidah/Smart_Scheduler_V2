# scheduler_core/solver.py
import time
import pandas as pd
from ortools.sat.python import cp_model
from .constraints import ConstraintBuilder

class SchedulerSolver:
    def __init__(self, scheduler_engine):
        self.se = scheduler_engine
        self.model = cp_model.CpModel()
        
        # Pustaka data dari engine utama
        self.mengajar = scheduler_engine.mengajar
        self.slot = scheduler_engine.slot
        self.rombel = scheduler_engine.rombel
        self.guru = scheduler_engine.guru
        self.col_jp = scheduler_engine.col_jp
        
        # Struktur variabel keputusan CP-SAT
        self.x = {}
        self.solver = cp_model.CpSolver()
        self.status = None
        
        self._build_variables()

    def _build_variables(self):
        """Membuat matriks keputusan boolean (0 atau 1) untuk setiap tugas mengajar dan slot waktu"""
        for m_idx, _ in self.mengajar.iterrows():
            for s_idx, _ in self.slot.iterrows():
                # x[m_idx, s_idx] bernilai 1 jika tugas mengajar m_idx ditempatkan pada slot s_idx, dan 0 jika tidak
                self.x[m_idx, s_idx] = self.model.NewBoolVar(f"x_{m_idx}_{s_idx}")

    def run_solver(self, timeout_seconds=60.0):
        """Menjalankan AI Solver untuk mencari solusi jadwal"""
        # Load constraints
        builder = ConstraintBuilder(self)
        builder.apply_all()
        
        # Atur parameter solver
        self.solver.parameters.max_time_in_seconds = float(timeout_seconds)
        
        # Cari Solusi
        self.status = self.solver.Solve(self.model)
        
        # Mengembalikan True jika solusi ditemukan (OPTIMAL atau FEASIBLE)
        return self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def extract_results(self):
        """Mengonversi hasil hitungan AI dari CP-SAT menjadi DataFrame pandas yang siap dibaca manusia"""
        hasil = []
        for m_idx, row_m in self.mengajar.iterrows():
            for s_idx, row_s in self.slot.iterrows():
                if self.solver.Value(self.x[m_idx, s_idx]) == 1:
                    hasil.append({
                        "Hari": row_s["Hari"],
                        "Jam_Ke": row_s["Jam_Ke"],
                        "ID_Rombel": row_m["ID_Rombel"],
                        "ID_Guru": row_m["ID_Guru"],
                        "ID_Mapel": row_m["ID_Mapel"]
                    })
        
        df_hasil = pd.DataFrame(hasil)
        
        # Urutkan berdasarkan hari dan jam pelajaran agar rapi
        if not df_hasil.empty:
            df_hasil = df_hasil.sort_values(by=["Hari", "Jam_Ke"]).reset_index(drop=True)
            
        return df_hasil
