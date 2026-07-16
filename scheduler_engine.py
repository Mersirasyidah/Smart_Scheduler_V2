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

    def optimize_schedule_quality(self, df):
        """
        Fungsi pengurutan tampilan jadwal:
        Mengurutkan hasil agar lebih rapi saat dibaca di Excel tanpa mengubah 
        kombinasi Hari & Jam asli dari solver untuk mencegah bentrok/duplikasi.
        """
        if df.empty:
            return df

        df_opt = df.copy()
        
        # Pastikan kolom-kolom penting tersedia
        kelas_col = "ID_Rombel" if "ID_Rombel" in df_opt.columns else ("Kelas" if "Kelas" in df_opt.columns else None)
        if not kelas_col:
            return df_opt

        # Urutkan secara logis: berdasarkan Kelas -> Hari -> Jam Ke
        # Ini adalah urutan standar yang paling aman dan tidak merusak struktur data asli
        df_opt = df_opt.sort_values(by=[kelas_col, "Hari", "Jam_Ke"]).reset_index(drop=True)
        return df_opt

    def export(self):
        if self.df_hasil.empty:
            return None
        
        # Urutkan secara aman
        df_optimized = self.optimize_schedule_quality(self.df_hasil)
        
        # JALUR KOMPATIBILITAS GANDA EXPORT:
        df_export = df_optimized.copy()
        
        if "ID_Guru" in df_export.columns:
            df_export["ID Guru"] = df_export["ID_Guru"]
        elif "ID Guru" in df_export.columns:
            df_export["ID_Guru"] = df_export["ID Guru"]
            
        if "Jam_Ke" in df_export.columns:
            df_export["Jam Ke"] = df_export["Jam_Ke"]
        elif "Jam Ke" in df_export.columns:
            df_export["Jam_Ke"] = df_export["Jam Ke"]
            
        # Duplikat data guru khusus untuk exporter (mencegah duplikasi data G26)
        exporter_guru = self.guru.copy()
        if "ID_Guru" in exporter_guru.columns:
            exporter_guru = exporter_guru.drop_duplicates(subset=["ID_Guru"], keep="first")
        elif "ID Guru" in exporter_guru.columns:
            exporter_guru = exporter_guru.drop_duplicates(subset=["ID Guru"], keep="first")
            
        if "ID_Guru" in exporter_guru.columns:
            exporter_guru["ID Guru"] = exporter_guru["ID_Guru"]
        if "Nama_Guru" in exporter_guru.columns:
            exporter_guru["Nama Guru"] = exporter_guru["Nama_Guru"]
            
        exporter_rombel = self.rombel.copy()
        if "ID_Rombel" in exporter_rombel.columns:
            exporter_rombel["Kelas"] = exporter_rombel["ID_Rombel"]
            
        clean_db = {
            "Guru": exporter_guru,
            "Guru_Mengajar": self.mengajar,
            "Rombel": exporter_rombel,
            "Mapel": self.mapel,
            "Hari_Jam": self.hari_jam
        }
        
        exporter = ScheduleExporter(df_export, clean_db)
        return exporter.generate_excel()
