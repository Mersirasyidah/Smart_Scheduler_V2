import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.model = cp_model.CpModel()
        self.solver = None

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

        # 2. Ekstraksi Tugas Mengajar
        self.tugas_mengajar = []
        tugas_id = 0
        mapel_mapping = dict(
            zip(self.mapel['Nama_Mapel'].str.strip().str.upper(), self.mapel['ID_Mapel'].astype(str).str.strip())
        )

        for _, row in self.mengajar.iterrows():
            guru = str(row["ID_Guru"]).strip()
            rombel = str(row["Kelas"]).strip() if "Kelas" in self.mengajar.columns else str(row["ID_Rombel"]).strip()
            mapel_nama = str(row["Mapel"]).strip().upper()
            mapel_id = mapel_mapping.get(mapel_nama, str(row.get("ID_Mapel", "M99")).strip())

            pembagian_str = str(row["Pembagian"]).strip()
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

        # Identifikasi Mapel PJOK
        self.mapel_pjok = set()
        for _, row in self.mapel.iterrows():
            kode = str(row["ID_Mapel"]).strip().upper()
            if kode in ["M11", "PJOK"] or "JASMANI" in str(row["Nama_Mapel"]).upper():
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
        # Inisialisasi Variabel Utama
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

        # =============================================================
        # ATURAN DASAR & FLEKSIBILITAS (MENCEGAH INFEASIBLE)
        # =============================================================
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            # Total jam mengajar harus sama dengan JP
            self.model.Add(
                sum(self.variables[(t_id, hari, jam)] for hari in self.list_hari for jam in self.jam_per_hari[hari]) == t["jp"]
            )
            # Setiap blok tugas hanya aktif di 1 hari
            self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1)

            # ---------------------------------------------------------
            # RELAKSASI 1: M01 (Agama) - Soft Constraint Berbobot Tinggi
            # ---------------------------------------------------------
            if mapel == "M01" and kamis_key:
                if rombel in ["7A", "8A", "8C", "9A"]:
                    # Utamakan Hari Kamis (Gunakan penalti jika di luar hari Kamis)
                    self.penalties.append((1 - tugas_hari_aktif[(t_id, kamis_key)]) * 200000)

                jam_target = []
                if rombel == "7A":
                    jam_target = [1, 2, 3]
                elif rombel in ["8A", "8C"]:
                    jam_target = [4, 5, 6]
                elif rombel == "9A":
                    jam_target = [7, 8, 9]

                # Beri penalti jika jam tidak sesuai target
                for jam in self.jam_per_hari[kamis_key]:
                    if jam_target and jam not in jam_target:
                        self.penalties.append(self.variables[(t_id, kamis_key, jam)] * 50000)

            # ---------------------------------------------------------
            # RELAKSASI 2: M09 & M10 Jam 1-4 untuk Kelas 9
            # ---------------------------------------------------------
            if mapel in ["M09", "M10"] and rombel.startswith("9"):
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 4:
                            self.penalties.append(self.variables[(t_id, hari, jam)] * 1000)

            # ---------------------------------------------------------
            # RELAKSASI 3: PJOK (M11) Jam 1-3
            # ---------------------------------------------------------
            if mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 6:
                            self.model.Add(self.variables[(t_id, hari, jam)] == 0)
                        elif jam > 3:
                            bobot = 300 if rombel.startswith("9") else 2500
                            self.penalties.append(self.variables[(t_id, hari, jam)] * bobot)

        # -------------------------------------------------------------
        # BATAS MAKSIMAL 6 JP PER GURU PER HARI
        # -------------------------------------------------------------
        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                self.model.Add(
                    sum(self.variables[(t_id, hari, jam)] for t_id in tugas_guru for jam in self.jam_per_hari[hari]) <= 6
                )

        # -------------------------------------------------------------
        # GURU G32 DIUTAMAKAN HARI KAMIS
        # -------------------------------------------------------------
        if "G32" in self.list_guru and kamis_key:
            tugas_g32 = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == "G32"]
            for hari in self.list_hari:
                if hari != kamis_key:
                    for t_id in tugas_g32:
                        self.penalties.append(tugas_hari_aktif[(t_id, hari)] * 50000)

        # -------------------------------------------------------------
        # ATURAN MGMP (GTT LIBUR / NON-GTT MAX JAM 3)
        # -------------------------------------------------------------
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            guru = t["guru"]
            mapel = t["mapel"]

            hari_mgmp_str = self.guru_mgmp_dict.get(guru) or self.mapel_mgmp_dict.get(mapel)

            if hari_mgmp_str:
                hari_mgmp_match = next((h for h in self.list_hari if h.strip().lower() == hari_mgmp_str.lower()), None)

                if hari_mgmp_match:
                    if guru in self.guru_gtt_set:
                        # Soft constraint jika beban JP terlalu padat
                        self.penalties.append(tugas_hari_aktif[(t_id, hari_mgmp_match)] * 100000)
                    else:
                        for jam in self.jam_per_hari[hari_mgmp_match]:
                            if jam > max_jam_mgmp_nongtt:
                                self.penalties.append(self.variables[(t_id, hari_mgmp_match, jam)] * 5000)

        # Maksimal Mapel per Hari per Rombel (Max 5)
        for rombel in self.list_rombel:
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

        for rombel in self.list_rombel:
            for mapel in self.list_mapel:
                tugas_sama = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel and t["mapel"] == mapel]
                if len(tugas_sama) > 1:
                    for hari in self.list_hari:
                        self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for t_id in tugas_sama) <= 1)

        # Mencegah Bentrok Rombel
        for rombel in self.list_rombel:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1)

        # Mencegah Bentrok Guru
        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_guru) <= 1)

        # Blok Jam Berurutan (Sliding Window)
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

        # Minimize Total Penalti
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
            return pd.DataFrame()

        rows = []
        tugas_lookup = {t["id_tugas"]: t for t in self.tugas_mengajar}

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

        df_hasil = pd.DataFrame(rows)
        if not df_hasil.empty:
            df_hasil = df_hasil.sort_values(by=["Hari", "ID_Rombel", "Jam_Ke"]).reset_index(drop=True)
            
        return df_hasil

    def generate_laporan_guru(self):
        df_hasil = self.extract_results()
        if df_hasil.empty:
            return pd.DataFrame()

        laporan_list = []
        for guru_id, group_guru in df_hasil.groupby("ID_Guru"):
            total_jp = len(group_guru)
            hari_list = group_guru["Hari"].unique().tolist()
            
            ringkasan_hari = []
            for hari in self.list_hari:
                if hari in hari_list:
                    sub_hari = group_guru[group_guru["Hari"] == hari]
                    rombel_jam = []
                    for rombel, sub_rombel in sub_hari.groupby("ID_Rombel"):
                        jam_min = sub_rombel["Jam_Ke"].min()
                        jam_max = sub_rombel["Jam_Ke"].max()
                        mapel = sub_rombel["ID_Mapel"].iloc[0]
                        
                        if jam_min == jam_max:
                            rombel_jam.append(f"{rombel}-{mapel} (Jam {jam_min})")
                        else:
                            rombel_jam.append(f"{rombel}-{mapel} (Jam {jam_min}-{jam_max})")
                    
                    ringkasan_hari.append(f"{hari}: " + ", ".join(rombel_jam))

            laporan_list.append({
                "ID_Guru": guru_id,
                "Total_JP": total_jp,
                "Jumlah_Hari_Mengajar": len(hari_list),
                "Hari_Mengajar": ", ".join(hari_list),
                "Rincian_Jadwal": " | ".join(ringkasan_hari)
            })

        return pd.DataFrame(laporan_list).sort_values(by="ID_Guru").reset_index(drop=True)
