import pandas as pd
from scheduler_core.solver import SchedulerSolver

class Scheduler:
    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df
        self.solver_instance = None

    def generate(self, timeout=120):
        self.solver_instance = SchedulerSolver(self)
        is_success = self.solver_instance.run_solver(timeout_seconds=timeout)
        
        if is_success:
            df_hasil = self.solver_instance.extract_results()
            # MENGAMBIL LAPORAN DETAIL GURU
            df_laporan_guru = self.solver_instance.generate_teacher_report(df_hasil)
            return df_hasil, df_laporan_guru
        else:
            return pd.DataFrame(), pd.DataFrame()
