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
        Fungsi Post-Processing untuk menyempurnakan kualitas jadwal:
        1. Menyatukan total jam mengajar guru mapel Blok (PJOK & Agama) agar langsung 3 JP berurutan penuh.
        2. Memastikan PJOK diletakkan di jam paling pagi (Jam 1, 2, 3).
        3. Menyatukan jam mengajar guru mapel non-blok lainnya agar tetap berurutan di hari yang sama.
        """
        if df.empty:
            return df

        df_opt = df.copy()
        
        # Deteksi kolom nama mapel yang sesungguhnya
        mapel_col = "Mapel" if "Mapel" in df_opt.columns else ("ID_Mapel" if "ID_Mapel" in df_opt.columns else None)
        if not mapel_col:
            return df_opt

        # Tentukan kolom kelas (menggunakan string tunggal agar aman di groupby)
        kelas_col = "ID_Rombel" if "ID_Rombel" in df_opt.columns else ("Kelas" if "Kelas" in df_opt.columns else None)
        if not kelas_col:
            return df_opt

        # Kata kunci kategori mapel wajib Blok & Prioritas Pagi
        kata_kunci_pjok = ["pjok", "olahraga", "jasmani", "penjas", "penjasorkes"]
        kata_kunci_agama = ["agama", "islam", "kristen", "katolik", "hindu", "buddha", "konghucu"]
        kata_kunci_blok = kata_kunci_pjok + kata_kunci_agama

        # FASE 1: Tarik seluruh pecahan jadwal PJOK / Agama ke dalam satu hari yang sama agar tidak terpencar beda hari
        # Kita lakukan pengecekan per Rombel/Kelas terlebih dahulu
        df_clean_days = []
        for kelas, group_kelas in df_opt.groupby(kelas_col):
            # Temukan mapel blok yang tersebar di kelas ini
            is_blok_mask = group_kelas[mapel_col].astype(str).str.lower().apply(
                lambda x: any(kunci in x for kunci in kata_kunci_blok)
            )
            
            df_blok = group_kelas[is_blok_mask].copy()
            df_biasa = group_kelas[~is_blok_mask].copy()

            if not df_blok.empty:
                # Satukan semua jam mapel blok yang sama ke hari pertama kemunculannya agar terkonsentrasi langsung 3 JP
                for mapel_name, mapel_group in df_blok.groupby(mapel_col):
                    hari_target = mapel_group["Hari"].iloc[0] # Pilih hari pertama
                    df_blok.loc[df_blok[mapel_col] == mapel_name, "Hari"] = hari_target
            
            df_clean_days.append(pd.concat([df_blok, df_biasa], ignore_index=True))
            
        df_opt = pd.concat(df_clean_days, ignore_index=True)

        # FASE 2: Urutkan susunan jam mengajar di setiap hari agar berurutan (Blok rapat & PJOK paling pagi)
        df_hasil_final = []

        # Iterasi menggunakan kolom kelas dan Hari
        for (kelas, hari), sub_df in df_opt.groupby([kelas_col, "Hari"]):
            # Urutkan berdasarkan Jam_Ke yang asli
            sub_df = sub_df.sort_values(by="Jam_Ke").reset_index(drop=True)
            
            # Klasifikasi baris berdasarkan jenis mata pelajaran
            is_pjok = sub_df[mapel_col].astype(str).str.lower().apply(
                lambda x: any(kunci in x for kunci in kata_kunci_pjok)
            )
            is_agama = sub_df[mapel_col].astype(str).str.lower().apply(
                lambda x: any(kunci in x for kunci in kata_kunci_agama)
            )
            is_blok = is_pjok | is_agama
            
            df_pjok = sub_df[is_pjok].copy()
            df_agama = sub_df[is_agama].copy()
            df_lain = sub_df[~is_blok].copy()
            
            # Gabungkan dengan prioritas urutan: 
            # 1. PJOK (paling pagi / atas)
            # 2. Agama (Blok berikutnya)
            # 3. Mata pelajaran biasa
            sub_df_sorted = pd.concat([df_pjok, df_agama, df_lain], ignore_index=True)
            
            # Pastikan guru non-blok yang tersisa juga berkumpul jam mengajarnya secara berurutan
            guru_col = "ID_Guru" if "ID_Guru" in sub_df_sorted.columns else ("ID Guru" if "ID Guru" in sub_df_sorted.columns else None)
            if guru_col:
                # Beri label urutan prioritas agar sorting guru biasa tidak merusak struktur blok PJOK & Agama di atas
                def tentukan_prioritas_tipe(row):
                    nama_mapel = str(row[mapel_col]).lower()
                    if any(k in nama_mapel for k in kata_kunci_pjok):
                        return 0 # PJOK paling atas
                    elif any(k in nama_mapel for k in kata_kunci_agama):
                        return 1 # Agama kedua
                    return 2 # Guru biasa berkumpul di bawah
                
                sub_df_sorted['tipe_sort'] = sub_df_sorted.apply(tentukan_prioritas_tipe, axis=1)
                
                # Urutkan berdasarkan tipe prioritas terlebih dahulu, lalu kelompokkan guru yang sama
                sub_df_sorted = sub_df_sorted.sort_values(
                    by=['tipe_sort', guru_col], 
                    ascending=[True, True]
                ).reset_index(drop=True)
                sub_df_sorted = sub_df_sorted.drop(columns=['tipe_sort'], errors='ignore')

            # Kembalikan penomoran Jam_Ke asli agar urutan jam sekolah tetap valid dan tidak bolong
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
        
        # Lakukan Optimasi Kualitas Jadwal (Urutan Jam Guru, Blok Agama/PJOK & Prioritas PJOK Pagi)
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
