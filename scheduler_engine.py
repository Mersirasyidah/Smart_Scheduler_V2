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
        Fungsi Post-Processing untuk:
        1. Menyatukan jam mengajar guru yang terpecah pada hari yang sama agar berurutan.
        2. Memprioritaskan PJOK (Olahraga) agar berada di jam-jam pagi (paling awal pada hari tersebut).
        """
        if df.empty:
            return df

        df_opt = df.copy()
        
        # Deteksi kolom nama mapel yang sesungguhnya
        mapel_col = "Mapel" if "Mapel" in df_opt.columns else ("ID_Mapel" if "ID_Mapel" in df_opt.columns else None)
        if not mapel_col:
            return df_opt

        # Definisikan kata kunci olahraga / PJOK
        kata_kunci_pjok = ["pjok", "olahraga", "jasmani", "penjas", "penjasorkes"]

        # Proses per-Kelas dan per-Hari agar jadwal tidak saling merusak batas kelas lain
        grup_kolom = ["ID_Rombel"] if "ID_Rombel" in df_opt.columns else ("Kelas" if "Kelas" in df_opt.columns else [])
        if not grup_kolom:
            return df_opt

        df_hasil_final = []

        # Iterasi per kelas dan per hari untuk merestrukturisasi urutan jam belajar
        for (kelas, hari), sub_df in df_opt.groupby([grup_kolom, "Hari"]):
            # Urutkan berdasarkan Jam_Ke yang asli
            sub_df = sub_df.sort_values(by="Jam_Ke").reset_index(drop=True)
            
            # Pisahkan antara baris PJOK dan Non-PJOK
            is_pjok = sub_df[mapel_col].astype(str).str.lower().apply(
                lambda x: any(kunci in x for kunci in kata_kunci_pjok)
            )
            
            df_pjok = sub_df[is_pjok].copy()
            df_lain = sub_df[~is_pjok].copy()
            
            # Satukan kembali dengan PJOK berada di paling atas (pagi hari)
            sub_df_sorted = pd.concat([df_pjok, df_lain], ignore_index=True)
            
            # Mengelompokkan guru yang sama agar jam mengajarnya berurutan setelah pergeseran PJOK
            # Kita urutkan berdasarkan Nama Guru / ID Guru agar jam mereka yang sama saling berdampingan
            guru_col = "ID_Guru" if "ID_Guru" in sub_df_sorted.columns else ("ID Guru" if "ID Guru" in sub_df_sorted.columns else None)
            if guru_col:
                # PJOK tetap dipertahankan di paling atas, sisanya diurutkan agar guru yang sama berkumpul jamnya
                sub_df_sorted['is_pjok_sort'] = is_pjok
                sub_df_sorted = sub_df_sorted.sort_values(
                    by=['is_pjok_sort', guru_col], 
                    ascending=[False, True]
                ).reset_index(drop=True)
                sub_df_sorted = sub_df_sorted.drop(columns=['is_pjok_sort'], errors='ignore')

            # Kembalikan alokasi nilai Jam_Ke asli yang berurutan ke struktur baris baru
            # Ini menjamin tidak ada jam bolong atau nomor jam yang rusak/hilang
            sub_df_sorted["Jam_Ke"] = sub_df["Jam_Ke"].values
            if "Jam" in sub_df_sorted.columns:
                sub_df_sorted["Jam"] = sub_df["Jam"].values
            if "Jam Ke" in sub_df_sorted.columns:
                sub_df_sorted["Jam Ke"] = sub_df["Jam Ke"].values
                
            df_hasil_final.append(sub_df_sorted)

        return pd.concat(df_hasil_final, ignore_index=True) if df_hasil_final else df_opt

    def export(self):
        if self.df_hasil.empty:
            return None
        
        # Lakukan Optimasi Kualitas Jadwal (Urutan Jam Guru & Prioritas PJOK Pagi)
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
