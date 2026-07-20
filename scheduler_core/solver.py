import pandas as pd
from ortools.sat.python import cp_model


# PASTIKAN NAMA KELAS DI BISA DIBACA 'SchedulerSolver'
class SchedulerSolver:

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.model = cp_model.CpModel()
        self.solver = None

        # Standardisasi Data & Logika Solver
        self.guru = scheduler.guru.copy()
        self.rombel = scheduler.rombel.copy()
        self.mengajar = scheduler.mengajar.copy()
        self.mapel = scheduler.mapel.copy()
        self.slot = scheduler.slot.copy()

        for df in [self.guru, self.rombel, self.mengajar, self.mapel, self.slot]:
            df.columns = [c.replace(" ", "_") for c in df.columns]

        self.list_guru = self.guru["ID_Guru"].tolist()
        self.list_rombel = self.rombel["Kelas"].tolist() if "Kelas" in self.rombel.columns else self.rombel["ID_Rombel"].tolist()
        self.list_mapel = self.mapel["ID_Mapel"].tolist()
        self.list_hari = self.slot["Hari"].unique().tolist()

        slot_belajar = self.slot[self.slot["Jenis"].str.upper() == "PEMBELAJARAN"]
        self.jam_per_hari = {}
        for hari in self.list_hari:
            self.jam_per_hari[hari] = sorted(
                slot_belajar[slot_belajar["Hari"] == hari]["Jam"].dropna().astype(int).tolist()
            )

        self.tugas_mengajar = []
        tugas_id = 0
        mapel_mapping = dict(zip(self.mapel['Nama_Mapel'].str.upper(), self.mapel['ID_Mapel']))
        
        for _, row in self.mengajar.iterrows():
            guru = row["ID_Guru"]
            rombel = row["Kelas"] if "Kelas" in self.mengajar.columns else row["ID_Rombel"]
            mapel_nama = str(row["Mapel"]).strip().upper()
            mapel_id = mapel_mapping.get(mapel_nama, row.get("ID_Mapel", "M99"))

            pembagian_str = str(row["Pembagian"]).strip()
            if "," in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(",") if x.strip().isdigit()]
            elif "." in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(".") if x.strip().isdigit()]
            else:
                try:
                    list_jp = [int(float(pembagian_str))]
                except:
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

        self.mapel_pjok = set()
        for _, row in self.mapel.iterrows():
            kode = str(row["ID_Mapel"]).strip().upper()
            if kode == "M11" or "JASMANI" in str(row["Nama_Mapel"]).upper():
                self.mapel_pjok.add(row["ID_Mapel"])

        self.variables = {}
        self.penalties = []

    def run_solver(self, timeout_seconds=120):
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

        # 1. HARD CONSTRAINTS
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            self.model.Add(
                sum(self.variables[(t_id, hari, jam)] for hari in self.list_hari for jam in self.jam_per_hari[hari]) == t["jp"]
            )
            self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1)

            # Agama M01 Kunci Hari Kamis untuk 7A, 8A, 8C, 9A
            if mapel == "M01" and rombel in ["7A", "8A", "8C", "9A"]:
                self.model.Add(tugas_hari_aktif[(t_id, "Kamis")] == 1)

            # PJOK M11 Jam <= 6
            if mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 6:
                            self.model.Add(self.variables[(t_id, hari, jam)] == 0)

        # Maksimal 4 Mapel
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
                    self.model.Add(sum(mapel_aktif_hari) <= 4)

        # Maksimal 1 Pertemuan per Hari
        for rombel in self.list_rombel:
            for mapel in self.list_mapel:
                tugas_sama = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel and t["mapel"] == mapel]
                if len(tugas_sama) > 1:
                    for hari in self.list_hari:
                        self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for t_id in tugas_sama) <= 1)

        # Konflik Rombel
        for rombel in self.list_rombel:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1)

        # Konflik Guru
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
                    for i in range(len(jam_hari) - target_jp + 1):
                        s_var = self.model.NewBoolVar(f"start_{t_id}_{hari}_{jam_hari[i]}")
                        start_vars.append(s_var)
                        for offset in range(target_jp):
                            self.model.Add(self.variables[(t_id, hari, jam_hari[i+offset])] == 1).OnlyEnforceIf(s_var)
                    self.model.Add(sum(start_vars) == tugas_hari_aktif[(t_id, hari)])

        # 2. SOFT CONSTRAINTS
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    if mapel in self.mapel_pjok and jam > 3:
                        self.penalties.append(self.variables[(t_id, hari, jam)] * 500)

        self.model.Minimize(sum(self.penalties))

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
