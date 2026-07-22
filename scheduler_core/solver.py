import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:

    def __init__(self, scheduler, df_jadwal_existing=None):
        """
        df_jadwal_existing: DataFrame berisi jadwal Kelas 7 & 8 yang sudah fixed/jadi.
        Harus punya kolom: ['Hari', 'Jam_Ke', 'ID_Rombel', 'ID_Guru', 'ID_Mapel']
        """
        self.scheduler = scheduler
        self.model = cp_model.CpModel()
        self.solver = None
        self.df_existing = df_jadwal_existing if df_jadwal_existing is not None else pd.DataFrame()

        # 1. Standardisasi Data & DataFrame
        self.guru = scheduler.guru.copy()
        self.rombel = scheduler.rombel.copy()
        self.mengajar = scheduler.mengajar.copy()
        self.mapel = scheduler.mapel.copy()
        self.slot = scheduler.slot.copy()

        for df in [self.guru, self.rombel, self.mengajar, self.mapel, self.slot]:
            df.columns = [c.replace(" ", "_") for c in df.columns]

        self.list_guru = self.guru["ID_Guru"].astype(str).str.strip().tolist()
        self.list_rombel = (
            self.rombel["Kelas"].astype(str).str.strip().tolist()
            if "Kelas" in self.rombel.columns
            else self.rombel["ID_Rombel"].astype(str).str.strip().tolist()
        )
        self.list_mapel = self.mapel["ID_Mapel"].astype(str).str.strip().tolist()
        self.list_hari = self.slot["Hari"].unique().tolist()

        slot_belajar = self.slot[self.slot["Jenis"].str.upper() == "PEMBELAJARAN"]
        self.jam_per_hari = {}
        for hari in self.list_hari:
            self.jam_per_hari[hari] = sorted(
                slot_belajar[slot_belajar["Hari"] == hari]["Jam"]
                .dropna()
                .astype(int)
                .tolist()
            )

        # 2. Ekstraksi Tugas Mengajar - HANYA UNTUK KELAS 9
        self.tugas_mengajar = []
        tugas_id = 0
        mapel_mapping = dict(
            zip(self.mapel['Nama_Mapel'].str.strip().str.upper(), self.mapel['ID_Mapel'].astype(str).str.strip())
        )

        for _, row in self.mengajar.iterrows():
            guru = str(row["ID_Guru"]).strip()
            rombel = str(row["Kelas"]).strip() if "Kelas" in self.mengajar.columns else str(row["ID_Rombel"]).strip()
            
            # FILTER HANYA KELAS 9
            if not rombel.startswith("9"):
                continue

            mapel_nama = str(row["Mapel"]).strip().upper()
            mapel_id = mapel_mapping.get(mapel_nama, str(row.get("ID_Mapel", "M99")).strip())

            # OVERRIDE PEMBAGIAN JP SANGAT KETAT (M09 -> 2,2,1 | M06 -> 2,2,2)
            if mapel_id == "M09":
                list_jp = [2, 2, 1]
            elif mapel_id == "M06":
                list_jp = [2, 2, 2]
            else:
                pembagian_str = str(row.get("Pembagian", "")).strip()
                if "," in pembagian_str:
                    list_jp = [int(x) for x in pembagian_str.split(",") if x.strip().isdigit()]
                elif "." in pembagian_str:
                    list_jp = [int(x) for x in pembagian_str.split(".") if x.strip().isdigit()]
                else:
                    try:
                        list_jp = [int(float(pembagian_str))]
                    except Exception:
                        list_jp = [int(row["JP"])]

            for jp_blok in list_jp:
                if jp_blok > 0:
                    self.tugas_mengajar.append({
                        "id_tugas": tugas_id,
                        "guru": guru,
                        "rombel": rombel,
                        "mapel": mapel_id,
                        "jp": jp_blok
                    })
                    tugas_id += 1

        # Identifikasi Mapel PJOK (M11)
        self.mapel_pjok = set()
        for _, row in self.mapel.iterrows():
            kode = str(row["ID_Mapel"]).strip().upper()
            if kode == "M11" or "JASMANI" in str(row["Nama_Mapel"].strip()).upper():
                self.mapel_pjok.add(str(row["ID_Mapel"]).strip())

        # 3. Deteksi Status GTT & Hari MGMP
        self.guru_gtt_set = set()
        self.guru_mgmp_dict = {}

        for _, row in self.guru.iterrows():
            g_id = str(row["ID_Guru"]).strip()
            status_str = ""
            for col in ["Status", "Kategori", "Status_Guru", "Jenis_Guru"]:
                if col in row and pd.notna(row[col]):
                    status_str += " " + str(row[col]).upper()
            if "GTT" in status_str or "HONOR" in status_str:
                self.guru_gtt_set.add(g_id)

            if "Hari_MGMP" in row and pd.notna(row["Hari_MGMP"]):
                self.guru_mgmp_dict[g_id] = str(row["Hari_MGMP"]).strip()

        self.mapel_mgmp_dict = {}
        if "Hari_MGMP" in self.mapel.columns:
            for _, row in self.mapel.iterrows():
                if pd.notna(row["Hari_MGMP"]):
                    m_id = str(row["ID_Mapel"]).strip()
                    self.mapel_mgmp_dict[m_id] = str(row["Hari_MGMP"]).strip()

        self.variables = {}
        self.penalties = []

    def run_solver(self, timeout_seconds=120, max_jam_mgmp_nongtt=3):
        # 1. Inisialisasi Variabel Utama untuk Kelas 9
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.variables[(t_id, hari, jam)] = self.model.NewBoolVar(f"t_{t_id}_{hari}_{jam}")

        tugas_hari_aktif = {}
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                tugas_hari_aktif[(t_id, hari)] = self.model.NewBoolVar(f"aktif_t_{t_id}_{hari}")
                self.model.AddMaxEquality(
                    tugas_hari_aktif[(t_id, hari)],
                    [self.variables[(t_id, hari, jam)] for jam in self.jam_per_hari[hari]]
                )

        kamis_key = next((h for h in self.list_hari if h.strip().lower() == "kamis"), None)

        # 2. Pre-Occupied Slots dari Jadwal Kelas 7 & 8
        guru_sibuk_existing = set()
        if not self.df_existing.empty:
            jam_col = "Jam_Ke" if "Jam_Ke" in self.df_existing.columns else "Jam"
            rombel_col = "ID_Rombel" if "ID_Rombel" in self.df_existing.columns else "Kelas"
            guru_col = "ID_Guru" if "ID_Guru" in self.df_existing.columns else "Guru"

            for _, row in self.df_existing.iterrows():
                r = str(row[rombel_col]).strip()
                if not r.startswith("9"):
                    h = str(row["Hari"]).strip()
                    j = int(row[jam_col])
                    g = str(row[guru_col]).strip()
                    guru_sibuk_existing.add((g, h, j))

        # 3. HARD CONSTRAINTS
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            rombel = t["rombel"]
            guru = t["guru"]
            jp = t["jp"]

            # Total JP per blok harus tepat
            self.model.Add(
                sum(self.variables[(t_id, hari, jam)] for hari in self.list_hari for jam in self.jam_per_hari[hari]) == jp
            )
            # Setiap blok hanya di 1 hari
            self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1)

            # Mencegah Bentrok dengan Kelas 7/8
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    if (guru, hari, jam) in guru_sibuk_existing:
                        self.model.Add(self.variables[(t_id, hari, jam)] == 0)

            # Aturan Khusus M01 9A Hari Kamis
            if mapel == "M01" and rombel == "9A" and kamis_key:
                target_jam = [7, 8, 9]
                if all(j in self.jam_per_hari[kamis_key] for j in target_jam):
                    self.model.Add(tugas_hari_aktif[(t_id, kamis_key)] == 1)
                    for jam in self.jam_per_hari[kamis_key]:
                        if jam in target_jam:
                            self.model.Add(self.variables[(t_id, kamis_key, jam)] == 1)
                        else:
                            self.model.Add(self.variables[(t_id, kamis_key, jam)] == 0)

            # M10 & PJOK (M11) Batas Maksimal Jam ke-6
            if mapel == "M10" or mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 6:
                            self.model.Add(self.variables[(t_id, hari, jam)] == 0)

        # 4. SOFT CONSTRAINT PRIORITAS M09 (Diberikan penalti sangat tinggi jika keluar Jam 1-2)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            if mapel == "M09":
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 2:
                            # Penalti 100.000 poin per jam jika di luar Jam 1-2
                            self.penalties.append(self.variables[(t_id, hari, jam)] * 100000)

        # 5. Aturan MGMP
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            guru = t["guru"]
            mapel = t["mapel"]

            hari_mgmp_str = self.guru_mgmp_dict.get(guru) or self.mapel_mgmp_dict.get(mapel)
            if hari_mgmp_str:
                hari_mgmp_match = next((h for h in self.list_hari if h.strip().lower() == hari_mgmp_str.lower()), None)

                if hari_mgmp_match:
                    if guru in self.guru_gtt_set:
                        self.model.Add(tugas_hari_aktif[(t_id, hari_mgmp_match)] == 0)
                    else:
                        for jam in self.jam_per_hari[hari_mgmp_match]:
                            if jam > max_jam_mgmp_nongtt:
                                self.penalties.append(self.variables[(t_id, hari_mgmp_match, jam)] * 5000)

        # Maksimal 5 Mapel per Hari per Rombel Kelas 9
        rombel_k9 = [r for r in self.list_rombel if r.startswith("9")]
        for rombel in rombel_k9:
            for hari in self.list_hari:
                mapel_aktif_hari = []
                for mapel in self.list_mapel:
                    tugas_mapel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel and t["mapel"] == mapel]
                    if tugas_mapel:
                        is_active = self.model.NewBoolVar(f"active_{rombel}_{mapel}_{hari}")
                        self.model.AddMaxEquality(is_active, [tugas_hari_aktif[(t_id, hari)] for t_id in tugas_mapel])
                        mapel_aktif_hari.append(is_active)
                
                if mapel_aktif_hari:
                    self.model.Add(sum(mapel_aktif_hari) <= 5)

        # Bentrok Internal Rombel & Guru
        for rombel in rombel_k9:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1)

        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_guru) <= 1)

        # Jam Berurutan Mandatori (Sliding Window)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            target_jp = t["jp"]
            if target_jp > 1:
                for hari in self.list_hari:
                    jam_hari = self.jam_per_hari[hari]
                    start_vars = []
                    num_windows = len(jam_hari) - target_jp + 1
                    
                    if num_windows > 0:
                        for i in range(num_windows):
                            s_var = self.model.NewBoolVar(f"start_{t_id}_{hari}_{jam_hari[i]}")
                            start_vars.append(s_var)
                            for offset in range(target_jp):
                                self.model.Add(self.variables[(t_id, hari, jam_hari[i + offset])] == 1).OnlyEnforceIf(s_var)
                        self.model.Add(sum(start_vars) == tugas_hari_aktif[(t_id, hari)])
                    else:
                        self.model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

        if self.penalties:
            self.model.Minimize(sum(self.penalties))

        # Eksekusi Solver
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = timeout_seconds
        self.solver.parameters.num_search_workers = 4
        status = self.solver.Solve(self.model)
        
        return status in [cp_model.OPTIMAL, cp_model.FEASIBLE]

    def extract_results(self):
        if self.solver is None:
            return self.df_existing

        rows = []
        tugas_lookup = {t["id_tugas"]: t for t in self.tugas_mengajar}

        # Ekstraksi Kelas 9
        for (t_id, hari, jam), var in self.variables.items():
            if self.solver.Value(var) == 1:
                t = tugas_lookup[t_id]
                rows.append({
                    "Hari": hari,
                    "Jam_Ke": jam, 
                    "ID_Rombel": t["rombel"], 
                    "ID_Guru": t["guru"],
                    "ID_Mapel": t["mapel"]
                })

        df_k9 = pd.DataFrame(rows)

        # Gabungkan dengan Kelas 7 & 8
        if not self.df_existing.empty:
            df_k78 = self.df_existing[~self.df_existing["ID_Rombel"].astype(str).str.startswith("9")].copy()
            df_gabungan = pd.concat([df_k78, df_k9], ignore_index=True)
        else:
            df_gabungan = df_k9

        if not df_gabungan.empty:
            df_gabungan = df_gabungan.sort_values(by=["Hari", "ID_Rombel", "Jam_Ke"]).reset_index(drop=True)
            
        return df_gabungan
