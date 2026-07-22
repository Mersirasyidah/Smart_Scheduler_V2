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

            # Breakdowns
            if mapel_id == "M09":
                list_jp = [2, 2, 1]  # Memaksa M09 dipecah 2, 2, dan 1 JP
            elif mapel_id == "M06":
                list_jp = [2, 2, 2]  # Memaksa M06 dipecah 2, 2, dan 2 JP
            else:
                pembagian_str = str(row.get("Pembagian", "")).strip()
                if "," in pembagian_str and pembagian_str != "nan":
                    list_jp = [int(x) for x in pembagian_str.split(",") if x.strip().isdigit()]
                elif "." in pembagian_str and pembagian_str != "nan":
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
            if kode == "M11" or "JASMANI" in str(row["Nama_Mapel"]).upper():
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
        # 1. Inisialisasi Variabel Utama
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

        # Constraints
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            rombel = t["rombel"]
            guru = t["guru"]
            jp = t["jp"]

            # Total jam mengajar sama dengan JP
            self.model.Add(
                sum(self.variables[(t_id, hari, jam)] for hari in self.list_hari for jam in self.jam_per_hari[hari]) == jp
            )
            # Setiap blok tugas hanya aktif di 1 hari
            self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1)

            # ATURAN KHUSUS GURU G32 (HANYA MENGAJAR HARI KAMIS)
            if guru == "G32":
                for hari in self.list_hari:
                    if hari.strip().lower() != "kamis":
                        self.model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

            # ATURAN KHUSUS M01 PADA HARI KAMIS
            if mapel == "M01" and kamis_key:
                target_jam = []
                if rombel == "7A":
                    target_jam = [1, 2, 3]
                elif rombel in ["8A", "8C"]:
                    target_jam = [4, 5, 6]
                elif rombel == "9A":
                    target_jam = [7, 8, 9]

                if target_jam:
                    self.model.Add(tugas_hari_aktif[(t_id, kamis_key)] == 1)
                    for jam in self.jam_per_hari[kamis_key]:
                        if jam in target_jam:
                            self.model.Add(self.variables[(t_id, kamis_key, jam)] == 1)
                        else:
                            self.model.Add(self.variables[(t_id, kamis_key, jam)] == 0)

            # PJOK Jam Maksimal Jam ke-6
            if mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 6:
                            self.model.Add(self.variables[(t_id, hari, jam)] == 0)

        # BATAS MAKSIMAL MENGAJAR GURU PER HARI (MAX 8 JP HARD, MAX 6 JP SOFT)
        for guru in self.list_guru:
            tugas_guru = [t for t in self.tugas_mengajar if t["guru"] == guru]
            if tugas_guru:
                for hari in self.list_hari:
                    total_jam_guru_hari = sum(
                        self.variables[(t["id_tugas"], hari, jam)]
                        for t in tugas_guru
                        for jam in self.jam_per_hari[hari]
                    )
                    # Hard Constraint: Max 8 JP
                    self.model.Add(total_jam_guru_hari <= 8)

                    # Soft Constraint: Penalti jika mengajar > 6 JP
                    over_6_var = self.model.NewIntVar(0, 2, f"over6_{guru}_{hari}")
                    self.model.Add(over_6_var >= total_jam_guru_hari - 6)
                    self.penalties.append(over_6_var * 20000)

        # SOFT CONSTRAINTS: KELAS 9 UNTUK MAPEL M09 & M10
        jam_diutamakan_kelas9 = {1, 2, 3, 4, 6}
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            if rombel.startswith("9") and mapel in ["M09", "M10"]:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam not in jam_diutamakan_kelas9:
                            self.penalties.append(self.variables[(t_id, hari, jam)] * 10000)

        # ATURAN MGMP: GTT MUTLAK LIBUR, NON-GTT SOFT
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

        # Maksimal 5 Mapel per Hari per Rombel
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

        # Maksimal 1 Pertemuan per Hari untuk Mapel yang Sama
        for rombel in self.list_rombel:
            for mapel in self.list_mapel:
                tugas_sama = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel and t["mapel"] == mapel]
                if len(tugas_sama) > 1:
                    for hari in self.list_hari:
                        self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for t_id in tugas_sama) <= 1)

        # Bentrok Rombel
        for rombel in self.list_rombel:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1)

        # Bentrok Guru
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

        if self.penalties:
            self.model.Minimize(sum(self.penalties))

        # Run CP-SAT Solver
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

    def generate_teacher_report(self, df_hasil):
        """Mengekstrak Laporan Harian Guru (Libur, Mengajar, Sela Jam Kosong)"""
        if df_hasil.empty:
            return pd.DataFrame()

        report_rows = []
        for guru in sorted(self.list_guru):
            df_guru = df_hasil[df_hasil["ID_Guru"] == guru]

            for hari in self.list_hari:
                df_guru_hari = df_guru[df_guru["Hari"] == hari]
                jam_tersedia = self.jam_per_hari.get(hari, [])

                if df_guru_hari.empty:
                    report_rows.append({
                        "ID_Guru": guru,
                        "Hari": hari,
                        "Status": "LIBUR",
                        "Total_JP": 0,
                        "Detail_Mengajar": "-",
                        "Jam_Kosong_Sela": "-"
                    })
                else:
                    df_sorted = df_guru_hari.sort_values(by="Jam_Ke")
                    jam_mengajar = df_sorted["Jam_Ke"].tolist()
                    total_jp = len(jam_mengajar)

                    detail_list = [f"Jam {r['Jam_Ke']} ({r['ID_Rombel']} - {r['ID_Mapel']})" for _, r in df_sorted.iterrows()]
                    detail_str = ", ".join(detail_list)

                    jam_min, jam_max = min(jam_mengajar), max(jam_mengajar)
                    jam_sela = [j for j in jam_tersedia if jam_min < j < jam_max and j not in jam_mengajar]
                    jam_sela_str = ", ".join([f"Jam {j}" for j in jam_sela]) if jam_sela else "Tidak Ada (Kontinu)"

                    report_rows.append({
                        "ID_Guru": guru,
                        "Hari": hari,
                        "Status": "MENGAJAR",
                        "Total_JP": total_jp,
                        "Detail_Mengajar": detail_str,
                        "Jam_Kosong_Sela": jam_sela_str
                    })

        return pd.DataFrame(report_rows)
