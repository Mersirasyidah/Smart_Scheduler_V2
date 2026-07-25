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
        # Mengirim kelima Dataframe langsung ke SchedulerSolver
        try:
            self.solver_instance = SchedulerSolver(
                self.guru, 
                self.rombel, 
                self.mengajar, 
                self.mapel, 
                self.slot
            )
        except TypeError:
            # Fallback jika Solver menggunakan kata kunci data_dict / kwargs
            try:
                self.solver_instance = SchedulerSolver(data={
                    "guru": self.guru,
                    "rombel": self.rombel,
                    "mengajar": self.mengajar,
                    "mapel": self.mapel,
                    "slot": self.slot
                })
            except Exception:
                # Fallback terakhir jika Solver memang menerima objek scheduler
                self.solver_instance = SchedulerSolver(self)

        # Jalankan solver
        is_success = self.solver_instance.run_solver(timeout_seconds=timeout)
        
        if is_success:
            df_hasil = self.solver_instance.extract_results()
            
            # Panggil fungsi laporan guru jika ada
            if hasattr(self.solver_instance, "generate_teacher_report"):
                df_laporan_guru = self.solver_instance.generate_teacher_report(df_hasil)
            else:
                df_laporan_guru = pd.DataFrame()
                
            return df_hasil, df_laporan_guru
        else:
            return pd.DataFrame(), pd.DataFrame()
