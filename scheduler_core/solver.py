import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.model = cp_model.CpModel()
        self.solver = None  # Tempat menyimpan status solver setelah run

        # =====================================================
        # DATA MASTER & STANDARDISASI KOLOM
        # =====================================================
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

        # =====================================================
        # PARSING BLOK JP DARI KOLOM PEMBAGIAN
        # =====================================================
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

        self.mapel_prioritas_pagi = set()
        self.mapel_pjok = set()
        self.mapel_prioritas_siang = set()

        for _, row in self.mapel.iterrows():
            kode = str(row["ID_Mapel"]).strip().upper()
            shift = str(row.get("Shift", "")).strip().upper()
            if kode == "M11" or "JASMANI" in str(row["Nama_Mapel"]).upper():
                self.mapel_pjok.add(row["ID_Mapel"])
            elif shift == "PAGI" or row.get("Prioritas", 3) == 1:
                self.mapel_prioritas_pagi.add(row["ID_Mapel"])
            elif shift == "SIANG":
                self.mapel_prioritas_siang.add(row["ID_Mapel"])

        self.variables = {}
        self.penalties = []

    def run_solver(self, timeout_seconds=120):
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

        # HARD CONSTRAINTS
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            self.model.Add(
                sum(self.variables[(t_id, hari, jam)] for hari in self.list_hari for jam in self.jam_per_hari[hari]) == t["jp"]
            )
            self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1)

        for rombel in self.list_rombel:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1)

        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(sum(self.variables[(t_id, hari, jam)] for t_id in tugas_guru) <= 1)

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

        # SOFT CONSTRAINTS
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    if mapel in self.mapel_pjok and jam > 6:
                        self.penalties.append(self.variables[(t_id, hari, jam)] * 100)
                    elif mapel in self.mapel_prioritas_pagi and jam > 6:
                        self.penalties.append(self.variables[(t_id, hari, jam)] * 50)
                    elif mapel in self.mapel_prioritas_siang and jam < 5:
                        self.penalties.append(self.variables[(t_id, hari, jam)] * 50)

        self.model.Minimize(sum(self.penalties))

        # Simpan objek solver ke instance class
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = timeout_seconds
        status = self.solver.Solve(self.model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print("✓ BERHASIL: Jadwal ditemukan!")
            return True
        else:
            print("× GAGAL: Tidak menemukan solusi.")
            return False

    def extract_results(self):
        """Mengekstrak variabel keputusan OR-Tools menjadi DataFrame output"""
        if self.solver is None:
            return pd.DataFrame()

        rows = []
        guru_dict = dict(zip(self.guru['ID_Guru'], self.guru['Nama_Guru']))
        mapel_dict = dict(zip(self.mapel['ID_Mapel'], self.mapel['Nama_Mapel']))

        # Mapping data sub-tugas berdasarkan id_tugas agar pemanggilan cepat
        tugas_lookup = {t["id_tugas"]: t for t in self.tugas_mengajar}

        for (t_id, hari, jam), var in self.variables.items():
            if self.solver.Value(var) == 1:
                t = tugas_lookup[t_id]
                rows.append({
                    "Hari": hari,
                    "Jam_Ke": jam, # <-- DIUBAH DI SINI (Sebelumnya "Jam")
                    "Kelas": t["rombel"],
                    "ID_Guru": t["guru"],
                    "Nama_Guru": guru_dict.get(t["guru"], "Unknown"),
                    "ID_Mapel": t["mapel"],
                    "Nama_Mapel": mapel_dict.get(t["mapel"], "Unknown"),
                })

        df_hasil = pd.DataFrame(rows)
        
        # Urutkan secara rapi berdasarkan Hari, Kelas, dan Jam_Ke
        if not df_hasil.empty:
            df_hasil = df_hasil.sort_values(by=["Hari", "Kelas", "Jam_Ke"]).reset_index(drop=True) # <-- DIUBAH DI SINI
            
        return df_hasil
