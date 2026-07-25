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

    def validate_data(self):
        """Mengecek kelayakan data sebelum dikirim ke solver"""
        warnings = []
        
        # 1. Cek Total JP Mengajar vs Total Slot
        if self.mengajar is not None and self.slot is not None and self.rombel is not None:
            # Ambil kolom JP (toleransi penamaan 'JP' atau 'Beban_JP' atau 'Jam')
            jp_col = next((c for c in self.mengajar.columns if 'jp' in c.lower() or 'jam' in c.lower()), None)
            
            if jp_col:
                total_jp_butuh = self.mengajar[jp_col].sum()
                total_slot_tersedia = len(self.slot) * len(self.rombel)
                
                if total_jp_butuh > total_slot_tersedia:
                    warnings.append(
                        f"⚠️ **Total JP Kurang Slot:** Total kebutuhan mengajar = **{total_jp_butuh} JP**, "
                        f"tetapi kapasitas slot kelas yang tersedia hanya **{total_slot_tersedia} JP** "
                        f"({len(self.slot)} slot × {len(self.rombel)} rombel)."
                    )

            # 2. Cek Guru dengan JP Melebihi Slot Jam Kerja
            guru_id_col = next((c for c in self.mengajar.columns if 'guru' in c.lower()), None)
            if jp_col and guru_id_col:
                jp_per_guru = self.mengajar.groupby(guru_id_col)[jp_col].sum()
                max_slot_guru = len(self.slot)
                guru_overload = jp_per_guru[jp_per_guru > max_slot_guru]
                
                if not guru_overload.empty:
                    for g_id, total_g_jp in guru_overload.items():
                        warnings.append(
                            f"⚠️ **Guru Overload:** Guru `{g_id}` memiliki beban **{total_g_jp} JP**, "
                            f"padahal total slot waktu seminggu hanya **{max_slot_guru} slot**."
                        )

        return warnings

    def generate(self, timeout=120):
        # 1. Jalankan Validasi Data Terlebih Dahulu
        validation_warnings = self.validate_data()
        if validation_warnings:
            st.warning("🔍 **Hasil Analisis Keselarasan Data Master:**")
            for warn in validation_warnings:
                st.write(warn)
            st.info("💡 Silakan perbaiki data Excel Anda terlebih dahulu jika terdapat keterbatasan kapasitas di atas.")

        # 2. Menentukan parameter days & max_hours_per_day
        days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
        max_hours = 8

        if self.slot is not None and not self.slot.empty:
            if 'Hari' in self.slot.columns:
                days = self.slot['Hari'].dropna().unique().tolist()
            
            for jam_col in ['Jam_Ke', 'Jam', 'JamKe']:
                if jam_col in self.slot.columns:
                    max_hours = int(self.slot[jam_col].max())
                    break

        # 3. Inisialisasi SchedulerSolver
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

        if hasattr(self.solver_instance, 'assignments') and self.solver_instance.assignments is None:
            self.solver_instance.assignments = []

        # 4. Jalankan Solver
        is_success = False
        try:
            if hasattr(self.solver_instance, 'solve'):
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
        except Exception as e:
            st.error(f"❌ Error saat menjalankan solver: {e}")
            st.code(traceback.format_exc())
            return pd.DataFrame(), pd.DataFrame()

        # 5. Ambil Hasil
        df_hasil = pd.DataFrame()
        if hasattr(self.solver_instance, "extract_results"):
            df_hasil = self.solver_instance.extract_results()
        elif hasattr(self.solver_instance, "get_schedule"):
            df_hasil = self.solver_instance.get_schedule()
        elif hasattr(self.solver_instance, "df_hasil"):
            df_hasil = getattr(self.solver_instance, "df_hasil")

        df_laporan_guru = pd.DataFrame()
        if hasattr(self.solver_instance, "generate_teacher_report") and not df_hasil.empty:
            try:
                df_laporan_guru = self.solver_instance.generate_teacher_report(df_hasil)
            except Exception:
                pass

        return df_hasil, df_laporan_guru
