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
            df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]

        # Sanitasi String (Hapus Spasi Liar)
        self.list_guru = self.guru["ID_Guru"].astype(str).str.strip().tolist()
        
        col_rombel = "Kelas" if "Kelas" in self.rombel.columns else "ID_Rombel"
        self.list_rombel = self.rombel[col_rombel].astype(str).str.strip().tolist()
        
        self.list_mapel = self.mapel["ID_Mapel"].astype(str).str.strip().tolist()
        self.list_hari = [str(h).strip() for h in self.slot["Hari"].unique() if pd.notna(h)]

        # Filter Slot Pembelajaran (Abaikan Kapitalisasi Teks)
        slot_belajar = self.slot[
            self.slot["Jenis"].astype(str).str.strip().str.upper() == "PEMBELAJARAN"
        ]
        
        self.jam_per_hari = {}
        for hari in self.list_hari:
            jams = (
                slot_belajar[slot_belajar["Hari"].astype(str).str.strip() == hari]["Jam"]
                .dropna()
                .astype(int)
                .tolist()
            )
            self.jam_per_hari[hari] = sorted(jams)

        # 2. Ekstraksi Tugas Mengajar
        self.tugas_mengajar = []
        tugas_id = 0
        
        # Mapping Mapel dari Teks ke ID
        mapel_mapping = {}
        if "Nama_Mapel" in self.mapel.columns and "ID_Mapel" in self.mapel.columns:
            mapel_mapping = dict(
                zip(
                    self.mapel["Nama_Mapel"].astype(str).str.strip().str.upper(),
                    self.mapel["ID_Mapel"].astype(str).str.strip(),
                )
            )

        col_mengajar_rombel = "Kelas" if "Kelas" in self.mengajar.columns else "ID_Rombel"

        for _, row in self.mengajar.iterrows():
            guru = str(row["ID_Guru"]).strip()
            rombel = str(row[col_mengajar_rombel]).strip()
            
            mapel_nama = str(row.get("Mapel", "")).strip().upper()
            mapel_id = mapel_mapping.get(
                mapel_nama, str(row.get("ID_Mapel", mapel_nama)).strip()
            )

            # Extract JP / Pembagian Blok
            pembagian_str = str(row.get("Pembagian", row.get("JP", "1"))).strip()
            list_jp = []
            
            if "," in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(",") if x.strip().isdigit()]
            elif "." in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(".") if x.strip().isdigit()]
            else:
                try:
                    list_jp = [int(float(pembagian_str))]
                except Exception:
                    list_jp = [int(row.get("JP", 1))]

            for jp_blok in list_jp:
                if jp_blok > 0:
                    self.tugas_mengajar.append({
                        "id_tugas": tugas_id,
                        "guru": guru,
                        "rombel": rombel,
                        "mapel": mapel_id,
                        "jp": jp_blok,
                    })
                    tugas_id += 1

        # Identifikasi Mapel PJOK
        self.mapel_pjok = set()
        for _, row in self.mapel.iterrows():
            kode = str(row.get("ID_Mapel", "")).strip().upper()
            nama = str(row.get("Nama_Mapel", "")).strip().upper()
            if kode in ["M11", "PJOK"] or "JASMANI" in nama or "PENJAS" in nama:
                self.mapel_pjok.add(str(row["ID_Mapel"]).strip())

        # Deteksi Status GTT & MGMP
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
                for jam in self.jam_per_hari.get(hari, []):
                    self.variables[(t_id, hari, jam)] = self.model.NewBoolVar(
                        f"t_{t_id}_{hari}_{jam}"
                    )

        tugas_hari_aktif = {}
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                tugas_hari_aktif[(t_id, hari)] = self.model.NewBoolVar(
                    f"aktif_t_{t_id}_{hari}"
                )
                jams = self.jam_per_hari.get(hari, [])
                if jams:
                    self.model.AddMaxEquality(
                        tugas_hari_aktif[(t_id, hari)],
                        [self.variables[(t_id, hari, jam)] for jam in jams],
                    )
                else:
                    self.model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

        kamis_key = next((h for h in self.list_hari if h.lower() == "kamis"), None)
        selasa_key = next((h for h in self.list_hari if h.lower() == "selasa"), None)

        # ATURAN DASAR
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            guru = t["guru"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            # Total jam mengajar harus sama dengan JP
            self.model.Add(
                sum(
                    self.variables[(t_id, hari, jam)]
                    for hari in self.list_hari
                    for jam in self.jam_per_hari.get(hari, [])
                )
                == t["jp"]
            )
            
            # Setiap blok tugas hanya aktif di 1 hari
            self.model.Add(
                sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1
            )

            # ATURAN 1: M01 (Agama - Penalti Lunak agar Tidak Crash)
            if mapel == "M01" and kamis_key:
                if rombel in ["7A", "8A", "8C", "9A"]:
                    self.penalties.append((1 - tugas_hari_aktif[(t_id, kamis_key)]) * 100000)

                jam_target = []
                if rombel == "7A": jam_target = [1, 2, 3]
                elif rombel in ["8A", "8C"]: jam_target = [4, 5, 6]
                elif rombel == "9A": jam_target = [7, 8, 9]

                for jam in self.jam_per_hari.get(kamis_key, []):
                    if jam_target and jam not in jam_target:
                        if (t_id, kamis_key, jam) in self.variables:
                            self.penalties.append(self.variables[(t_id, kamis_key, jam)] * 50000)

            # ATURAN 2: G32
            if guru == "G32" and kamis_key:
                if rombel == "8B":
                    self.penalties.append((1 - tugas_hari_aktif[(t_id, kamis_key)]) * 100000)

                if selasa_key:
                    self.penalties.append(tugas_hari_aktif[(t_id, selasa_key)] * 50000)

            # RELAKSASI: M09 & M10
            if mapel in ["M09", "M10"] and rombel.startswith("9"):
                for hari in self.list_hari:
                    for jam in self.jam_per_hari.get(hari, []):
                        if jam > 4 and (t_id, hari, jam) in self.variables:
                            self.penalties.append(self.variables[(t_id, hari, jam)] * 1000)

            # RELAKSASI: PJOK
            if mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari.get(hari, []):
                        if (t_id, hari, jam) in self.variables:
                            if jam > 6:
                                self.model.Add(self.variables[(t_id, hari, jam)] == 0)
                            elif jam > 3:
                                bobot = 300 if rombel.startswith("9") else 2500
                                self.penalties.append(self.variables[(t_id, hari, jam)] * bobot)

        # BATAS MAKSIMAL JAM GURU PER HARI (Dibuat Max 8 JP agar Lebih Fleksibel)
        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                jams = self.jam_per_hari.get(hari, [])
                if jams and tugas_guru:
                    self.model.Add(
                        sum(
                            self.variables[(t_id, hari, jam)]
                            for t_id in tugas_guru
                            for jam in jams
                            if (t_id, hari, jam) in self.variables
                        )
                        <= 8  # Dinaikkan ke 8 agar toleran untuk guru dengan JP besar
                    )

        # MENCEGAH BENTROK ROMBEL
        for rombel in self.list_rombel:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari.get(hari, []):
                    self.model.Add(
                        sum(
                            self.variables[(t_id, hari, jam)]
                            for t_id in tugas_rombel
                            if (t_id, hari, jam) in self.variables
                        )
                        <= 1
                    )

        # MENCEGAH BENTROK GURU
        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                for jam in self.jam_per_hari.get(hari, []):
                    self.model.Add(
                        sum(
                            self.variables[(t_id, hari, jam)]
                            for t_id in tugas_guru
                            if (t_id, hari, jam) in self.variables
                        )
                        <= 1
                    )

        # BLOK JAM BERURUTAN (Sliding Window)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            target_jp = t["jp"]
            if target_jp > 1:
                for hari in self.list_hari:
                    jam_hari = self.jam_per_hari.get(hari, [])
                    start_vars = []
                    num_windows = len(jam_hari) - target_jp + 1

                    if num_windows > 0:
                        for i in range(num_windows):
                            s_var = self.model.NewBoolVar(f"start_{t_id}_{hari}_{jam_hari[i]}")
                            start_vars.append(s_var)
                            for offset in range(target_jp):
                                j_target = jam_hari[i + offset]
                                if (t_id, hari, j_target) in self.variables:
                                    self.model.Add(
                                        self.variables[(t_id, hari, j_target)] == 1
                                    ).OnlyEnforceIf(s_var)
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

        print(f"Status Solver: {self.solver.StatusName(status)}")
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
                    "ID_Mapel": t["mapel"],
                })

        df_hasil = pd.DataFrame(rows)
        if not df_hasil.empty:
            df_hasil = df_hasil.sort_values(
                by=["Hari", "ID_Rombel", "Jam_Ke"]
            ).reset_index(drop=True)

        return df_hasil
