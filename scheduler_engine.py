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
        # 1. Menentukan parameter days & max_hours_per_day secara otomatis dari DataFrame slot
        days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
        max_hours = 8

        if self.slot is not None and not self.slot.empty:
            # Ambil daftar hari unik dari slot jika ada kolom 'Hari'
            if 'Hari' in self.slot.columns:
                days = self.slot['Hari'].dropna().unique().tolist()
            
            # Ambil max jam per hari dari slot jika ada kolom 'Jam_Ke' atau 'Jam'
            if 'Jam_Ke' in self.slot.columns:
                max_hours = int(self.slot['Jam_Ke'].max())
            elif 'Jam' in self.slot.columns:
                max_hours = int(self.slot['Jam'].max())

        # 2. Inisialisasi SchedulerSolver dengan 3 argumen wajib
        init_errors = []

        # Percobaan A: Passing self, days, max_hours_per_day
        try:
            self.solver_instance = SchedulerSolver(self, days, max_hours)
        except Exception as e1:
            init_errors.append(f"Percobaan A (Self, Days, MaxHours) Gagal: {e1}")
            
            # Percobaan B: Passing data dict/tuple jika SchedulerSolver butuh data langsung
            try:
                data_dict = {
                    "guru": self.guru,
                    "rombel": self.rombel,
                    "mengajar": self.mengajar,
                    "mapel": self.mapel,
                    "slot": self.slot
                }
                self.solver_instance = SchedulerSolver(data_dict, days, max_hours)
            except Exception as e2:
                init_errors.append(f"Percobaan B (DataDict, Days, MaxHours) Gagal: {e2}")

        if self.solver_instance is None:
            st.error("❌ Detail Error Inisialisasi SchedulerSolver:")
            for err in init_errors:
                st.code(err)
            return pd.DataFrame(), pd.DataFrame()

        # 3. Jalankan solver
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
