import pandas as pd
import traceback
import streamlit as st
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
        # Coba beberapa pola inisialisasi SchedulerSolver
        init_errors = []

        # Opsi 1: Passing 5 Dataframe langsung sebagai argumen posisi
        try:
            self.solver_instance = SchedulerSolver(
                self.guru, 
                self.rombel, 
                self.mengajar, 
                self.mapel, 
                self.slot
            )
        except Exception as e1:
            init_errors.append(f"Percobaan 1 (Positional Args) Gagal: {e1}")
            
            # Opsi 2: Passing dict data
            try:
                self.solver_instance = SchedulerSolver(data={
                    "guru": self.guru,
                    "rombel": self.rombel,
                    "mengajar": self.mengajar,
                    "mapel": self.mapel,
                    "slot": self.slot
                })
            except Exception as e2:
                init_errors.append(f"Percobaan 2 (Dict Arg) Gagal: {e2}")
                
                # Opsi 3: Passing self
                try:
                    self.solver_instance = SchedulerSolver(self)
                except Exception as e3:
                    init_errors.append(f"Percobaan 3 (Self Arg) Gagal: {e3}")

        # Jika semua opsi inisialisasi gagal, tampilkan detail error di Streamlit
        if self.solver_instance is None:
            st.error("❌ Detail Error Inisialisasi SchedulerSolver:")
            for err in init_errors:
                st.code(err)
            return pd.DataFrame(), pd.DataFrame()

        # Jalankan solver
        try:
            is_success = self.solver_instance.run_solver(timeout_seconds=timeout)
        except Exception as e:
            st.error(f"❌ Error saat menjalankan run_solver: {e}")
            st.code(traceback.format_exc())
            return pd.DataFrame(), pd.DataFrame()
        
        if is_success:
            df_hasil = self.solver_instance.extract_results()
            
            if hasattr(self.solver_instance, "generate_teacher_report"):
                df_laporan_guru = self.solver_instance.generate_teacher_report(df_hasil)
            else:
                df_laporan_guru = pd.DataFrame()
                
            return df_hasil, df_laporan_guru
        else:
            return pd.DataFrame(), pd.DataFrame()
