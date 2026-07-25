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
        # 1. Menentukan parameter days & max_hours_per_day dari DataFrame slot
        days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
        max_hours = 8

        if self.slot is not None and not self.slot.empty:
            if 'Hari' in self.slot.columns:
                days = self.slot['Hari'].dropna().unique().tolist()
            
            if 'Jam_Ke' in self.slot.columns:
                max_hours = int(self.slot['Jam_Ke'].max())
            elif 'Jam' in self.slot.columns:
                max_hours = int(self.slot['Jam'].max())

        # 2. Inisialisasi SchedulerSolver
        try:
            self.solver_instance = SchedulerSolver(self, days, max_hours)
        except Exception:
            try:
                data_dict = {
                    "guru": self.guru,
                    "rombel": self.rombel,
                    "mengajar": self.mengajar,
                    "mapel": self.mapel,
                    "slot": self.slot
                }
                self.solver_instance = SchedulerSolver(data_dict, days, max_hours)
            except Exception as e:
                st.error(f"❌ Gagal menginisialisasi SchedulerSolver: {e}")
                return pd.DataFrame(), pd.DataFrame()

        # Jaminan bahwa self.assignments tidak None sebelum solve dijalankan
        if hasattr(self.solver_instance, 'assignments') and self.solver_instance.assignments is None:
            self.solver_instance.assignments = []

        # 3. Jalankan method solve
        is_success = False
        try:
            if hasattr(self.solver_instance, 'solve'):
                # Coba passing parameter timeout jika diterima oleh solve()
                try:
                    result = self.solver_instance.solve(time_limit=timeout)
                except TypeError:
                    try:
                        result = self.solver_instance.solve(timeout=timeout)
                    except TypeError:
                        result = self.solver_instance.solve()
                
                if isinstance(result, bool):
                    is_success = result
                elif result is not None:
                    is_success = True
            else:
                st.error("❌ Method solve() tidak ditemukan pada SchedulerSolver.")
                return pd.DataFrame(), pd.DataFrame()
        except Exception as e:
            st.error(f"❌ Error saat menjalankan solver: {e}")
            st.code(traceback.format_exc())
            return pd.DataFrame(), pd.DataFrame()

        # 4. Ambil hasil jadwal
        df_hasil = pd.DataFrame()
        if hasattr(self.solver_instance, "extract_results"):
            df_hasil = self.solver_instance.extract_results()
        elif hasattr(self.solver_instance, "get_schedule"):
            df_hasil = self.solver_instance.get_schedule()
        elif hasattr(self.solver_instance, "get_results"):
            df_hasil = self.solver_instance.get_results()
        elif hasattr(self.solver_instance, "df_hasil"):
            df_hasil = getattr(self.solver_instance, "df_hasil")

        # 5. Ambil laporan detail guru jika ada
        df_laporan_guru = pd.DataFrame()
        if hasattr(self.solver_instance, "generate_teacher_report") and not df_hasil.empty:
            try:
                df_laporan_guru = self.solver_instance.generate_teacher_report(df_hasil)
            except Exception:
                pass

        return df_hasil, df_laporan_guru
