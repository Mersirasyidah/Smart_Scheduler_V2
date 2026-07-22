import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.guru = scheduler.guru.copy()
        self.rombel = scheduler.rombel.copy()
        self.mengajar = scheduler.mengajar.copy()
        self.mapel = scheduler.mapel.copy()
        self.slot = scheduler.slot.copy()

        # Standardisasi kolom
        for df in [self.guru, self.rombel, self.mengajar, self.mapel, self.slot]:
            df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]

        self.list_guru = self.guru["ID_Guru"].astype(str).str.strip().tolist()

        col_rombel = (
            "Kelas" if "Kelas" in self.rombel.columns else "ID_Rombel"
        )
        self.list_rombel = (
            self.rombel[col_rombel].astype(str).str.strip().tolist()
        )

        self.list_mapel = (
            self.mapel["ID_Mapel"].astype(str).str.strip().tolist()
        )
        self.list_hari = [
            str(h).strip() for h in self.slot["Hari"].unique() if pd.notna(h)
        ]

        # Filter Slot Pembelajaran
        slot_belajar = self.slot[
            self.slot["Jenis"].astype(str).str.strip().str.upper()
            == "PEMBELAJARAN"
        ]

        self.jam_per_hari = {}
        for hari in self.list_hari:
            jams = (
                slot_belajar[
                    slot_belajar["Hari"].astype(str).str.strip() == hari
                ]["Jam"]
                .dropna()
                .astype(int)
                .tolist()
            )
            self.jam_per_hari[hari] = sorted(jams)

        # Parsing Tugas Mengajar
        self.tugas_mengajar = []
        tugas_id = 0

        mapel_mapping = {}
        if (
            "Nama_Mapel" in self.mapel.columns
            and "ID_Mapel" in self.mapel.columns
        ):
            mapel_mapping = dict(
                zip(
                    self.mapel["Nama_Mapel"]
                    .astype(str)
                    .str.strip()
                    .str.upper(),
                    self.mapel["ID_Mapel"].astype(str).str.strip(),
                )
            )

        col_mengajar_rombel = (
            "Kelas" if "Kelas" in self.mengajar.columns else "ID_Rombel"
        )

        for _, row in self.mengajar.iterrows():
            guru = str(row["ID_Guru"]).strip()
            rombel = str(row[col_mengajar_rombel]).strip()

            mapel_nama = str(row.get("Mapel", "")).strip().upper()
            mapel_id = mapel_mapping.get(
                mapel_nama, str(row.get("ID_Mapel", mapel_nama)).strip()
            )

            pembagian_str = str(
                row.get("Pembagian", row.get("JP", "1"))
            ).strip()
            list_jp = []

            if "," in pembagian_str:
                list_jp = [
                    int(x) for x in pembagian_str.split(",") if x.strip().isdigit()
                ]
            elif "." in pembagian_str:
                list_jp = [
                    int(x) for x in pembagian_str.split(".") if x.strip().isdigit()
                ]
            else:
                try:
                    list_jp = [int(float(pembagian_str))]
                except Exception:
                    list_jp = [int(row.get("JP", 1))]

            for jp_blok in list_jp:
                if jp_blok > 0:
                    self.tugas_mengajar.append(
                        {
                            "id_tugas": tugas_id,
                            "guru": guru,
                            "rombel": rombel,
                            "mapel": mapel_id,
                            "jp": jp_blok,
                        }
                    )
                    tugas_id += 1

        # Mapping Libur / MGMP Guru
        self.guru_mgmp_dict = {}
        for _, row in self.guru.iterrows():
            g_id = str(row["ID_Guru"]).strip()
            for col_mgmp in ["Hari_MGMP", "Hari_Libur", "Libur", "MGMP"]:
                if col_mgmp in row and pd.notna(row[col_mgmp]):
                    val = str(row[col_mgmp]).strip()
                    if val and val.lower() != "nan" and val != "-":
                        self.guru_mgmp_dict[g_id] = val
                        break

    def build_and_solve(self, timeout_seconds=60, max_jp_limit=6):
        model = cp_model.CpModel()
        variables = {}
        penalties = []

        # Variabel Utama
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari.get(hari, []):
                    variables[(t_id, hari, jam)] = model.NewBoolVar(
                        f"t_{t_id}_{hari}_{jam}"
                    )

        tugas_hari_aktif = {}
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                tugas_hari_aktif[(t_id, hari)] = model.NewBoolVar(
                    f"aktif_{t_id}_{hari}"
                )
                jams = self.jam_per_hari.get(hari, [])
                if jams:
                    model.AddMaxEquality(
                        tugas_hari_aktif[(t_id, hari)],
                        [variables[(t_id, hari, jam)] for jam in jams],
                    )
                else:
                    model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

        # 1. ATURAN HARD: Beban JP Harus Terpenuhi & Cuma 1 Hari per Blok Tugas
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            model.Add(
                sum(
                    variables[(t_id, hari, jam)]
                    for hari in self.list_hari
                    for jam in self.jam_per_hari.get(hari, [])
                )
                == t["jp"]
            )
            model.Add(
                sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1
            )

        # 2. ATURAN HARD: DILARANG MENGAJAR DI HARI LIBUR / MGMP
        for guru, hari_libur in self.guru_mgmp_dict.items():
            target_hari = next(
                (h for h in self.list_hari if h.lower() == hari_libur.lower()), None
            )
            if target_hari:
                tugas_guru = [
                    t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
                ]
                for t_id in tugas_guru:
                    for jam in self.jam_per_hari.get(target_hari, []):
                        if (t_id, target_hari, jam) in variables:
                            model.Add(variables[(t_id, target_hari, jam)] == 0)

        # 3. ATURAN HARD: Tidak Bentrok Rombel
        for rombel in self.list_rombel:
            tugas_rombel = [
                t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel
            ]
            for hari in self.list_hari:
                for jam in self.jam_per_hari.get(hari, []):
                    model.Add(
                        sum(
                            variables[(t_id, hari, jam)]
                            for t_id in tugas_rombel
                            if (t_id, hari, jam) in variables
                        )
                        <= 1
                    )

        # 4. ATURAN HARD: Tidak Bentrok Guru
        for guru in self.list_guru:
            tugas_guru = [
                t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
            ]
            for hari in self.list_hari:
                for jam in self.jam_per_hari.get(hari, []):
                    model.Add(
                        sum(
                            variables[(t_id, hari, jam)]
                            for t_id in tugas_guru
                            if (t_id, hari, jam) in variables
                        )
                        <= 1
                    )

        # 5. ATURAN BATAS MAX JP PER HARI PER GURU
        for guru in self.list_guru:
            tugas_guru = [
                t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
            ]
            for hari in self.list_hari:
                jams = self.jam_per_hari.get(hari, [])
                if jams and tugas_guru:
                    model.Add(
                        sum(
                            variables[(t_id, hari, jam)]
                            for t_id in tugas_guru
                            for jam in jams
                            if (t_id, hari, jam) in variables
                        )
                        <= max_jp_limit
                    )

        # 6. JAM BERURUTAN (Blok JP)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            target_jp = t["jp"]
            if target_jp > 1:
                for hari in self.list_hari:
                    jam_hari = self.jam_per_hari.get(hari, [])
                    num_windows = len(jam_hari) - target_jp + 1
                    if num_windows > 0:
                        start_vars = []
                        for i in range(num_windows):
                            s_var = model.NewBoolVar(
                                f"start_{t_id}_{hari}_{jam_hari[i]}"
                            )
                            start_vars.append(s_var)
                            for offset in range(target_jp):
                                j_target = jam_hari[i + offset]
                                if (t_id, hari, j_target) in variables:
                                    model.Add(
                                        variables[(t_id, hari, j_target)] == 1
                                    ).OnlyEnforceIf(s_var)
                        model.Add(sum(start_vars) == tugas_hari_aktif[(t_id, hari)])
                    else:
                        model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        solver.parameters.num_search_workers = 4
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return solver, variables
        return None, None


class SchedulerEngine:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df

    def generate(self, timeout=120):
        solver_obj = SchedulerSolver(self)

        # METODE STRATEGI BERTAHAP (FALLBACK)
        # 1. Coba Max 6 JP per hari
        # 2. Jika gagal, coba Max 7 JP per hari
        # 3. Jika gagal, coba Max 8 JP per hari
        for limit_jp in [6, 7, 8]:
            print(f"Mencoba mencari jadwal dengan batas max {limit_jp} JP/hari...")
            solver, variables = solver_obj.build_and_solve(
                timeout_seconds=timeout // 3, max_jp_limit=limit_jp
            )

            if solver is not None:
                # Ekstraksi Hasil
                rows = []
                tugas_lookup = {t["id_tugas"]: t for t in solver_obj.tugas_mengajar}
                for (t_id, hari, jam), var in variables.items():
                    if solver.Value(var) == 1:
                        t = tugas_lookup[t_id]
                        rows.append(
                            {
                                "Hari": hari,
                                "Jam_Ke": jam,
                                "ID_Rombel": t["rombel"],
                                "ID_Guru": t["guru"],
                                "ID_Mapel": t["mapel"],
                            }
                        )

                df_hasil = (
                    pd.DataFrame(rows)
                    .sort_values(by=["Hari", "ID_Rombel", "Jam_Ke"])
                    .reset_index(drop=True)
                )

                # Generate Rekap Laporan Guru
                df_laporan_guru = (
                    df_hasil.groupby(["ID_Guru", "Hari"])
                    .agg(
                        Total_JP=("Jam_Ke", "count"),
                        Detail_Kelas=(
                            "ID_Rombel",
                            lambda x: ", ".join(sorted(set(x))),
                        ),
                    )
                    .reset_index()
                )

                return df_hasil, df_laporan_guru

        # Jika 6, 7, dan 8 JP tetap gagal
        return pd.DataFrame(), pd.DataFrame()


Scheduler = SchedulerEngine
