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

        # 2. Ekstraksi Tugas Mengajar
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

        # Identifikasi Mapel PJOK
        self.mapel_pjok = set()
        for _, row in self.mapel.iterrows():
            kode = str(row.get("ID_Mapel", "")).strip().upper()
            nama = str(row.get("Nama_Mapel", "")).strip().upper()
            if kode in ["M11", "PJOK"] or "JASMANI" in nama or "PENJAS" in nama:
                self.mapel_pjok.add(str(row["ID_Mapel"]).strip())

        # Deteksi Hari MGMP / Hari Libur Per Guru
        self.guru_mgmp_dict = {}
        for _, row in self.guru.iterrows():
            g_id = str(row["ID_Guru"]).strip()
            for col_mgmp in ["Hari_MGMP", "Hari_Libur", "Libur", "MGMP"]:
                if col_mgmp in row and pd.notna(row[col_mgmp]):
                    val = str(row[col_mgmp]).strip()
                    if val and val.lower() != "nan" and val != "-":
                        self.guru_mgmp_dict[g_id] = val
                        break

        self.variables = {}
        self.penalties = []

    def run_solver(self, timeout_seconds=180, target_max_jp=6):
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

        # CONSTRAINTS UTAMA
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            guru = t["guru"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            # Total jam mengajar harus sesuai JP
            self.model.Add(
                sum(
                    self.variables[(t_id, hari, jam)]
                    for hari in self.list_hari
                    for jam in self.jam_per_hari.get(hari, [])
                )
                == t["jp"]
            )

            # 1 blok tugas hanya di 1 hari
            self.model.Add(
                sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1
            )

            # Aturan Khusus M01 & G32
            if mapel == "M01" and kamis_key:
                if rombel in ["7A", "8A", "8C", "9A"]:
                    self.penalties.append((1 - tugas_hari_aktif[(t_id, kamis_key)]) * 50000)

            if guru == "G32" and kamis_key:
                if rombel == "8B":
                    self.penalties.append((1 - tugas_hari_aktif[(t_id, kamis_key)]) * 50000)

            # PJOK (Hindari Jam Siang)
            if mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari.get(hari, []):
                        if (t_id, hari, jam) in self.variables:
                            if jam > 6:
                                self.model.Add(self.variables[(t_id, hari, jam)] == 0)
                            elif jam > 3:
                                self.penalties.append(self.variables[(t_id, hari, jam)] * 1000)

        # HARI LIBUR / MGMP GURU (Kunci Mati / Hard Constraint)
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
                        if (t_id, target_hari, jam) in self.variables:
                            self.model.Add(self.variables[(t_id, target_hari, jam)] == 0)

        # BEBAN MENGAJAR PER HARI (Soft Constraint: Target 6 JP, Penalti jika lebih)
        for guru in self.list_guru:
            tugas_guru = [
                t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
            ]
            for hari in self.list_hari:
                jams = self.jam_per_hari.get(hari, [])
                if jams and tugas_guru:
                    total_jam_hari = sum(
                        self.variables[(t_id, hari, jam)]
                        for t_id in tugas_guru
                        for jam in jams
                        if (t_id, hari, jam) in self.variables
                    )
                    # Beri penalti tinggi jika melebihi 6 JP agar solver berusaha keras membatasinya di 6 JP
                    lebih_jp = self.model.NewIntVar(0, 10, f"lebih_{guru}_{hari}")
                    self.model.Add(total_jam_hari - target_max_jp <= lebih_jp)
                    self.penalties.append(lebih_jp * 10000)

        # BENTROK ROMBEL & GURU
        for rombel in self.list_rombel:
            tugas_rombel = [
                t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel
            ]
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

        for guru in self.list_guru:
            tugas_guru = [
                t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
            ]
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

        # JAM BERURUTAN (Sliding Window)
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
                            s_var = self.model.NewBoolVar(
                                f"start_{t_id}_{hari}_{jam_hari[i]}"
                            )
                            start_vars.append(s_var)
                            for offset in range(target_jp):
                                j_target = jam_hari[i + offset]
                                if (t_id, hari, j_target) in self.variables:
                                    self.model.Add(
                                        self.variables[(t_id, hari, j_target)] == 1
                                    ).OnlyEnforceIf(s_var)
                        self.model.Add(
                            sum(start_vars) == tugas_hari_aktif[(t_id, hari)]
                        )
                    else:
                        self.model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

        if self.penalties:
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
                rows.append(
                    {
                        "Hari": hari,
                        "Jam_Ke": jam,
                        "ID_Rombel": t["rombel"],
                        "ID_Guru": t["guru"],
                        "ID_Mapel": t["mapel"],
                    }
                )

        df_hasil = pd.DataFrame(rows)
        if not df_hasil.empty:
            df_hasil = df_hasil.sort_values(
                by=["Hari", "ID_Rombel", "Jam_Ke"]
            ).reset_index(drop=True)

        return df_hasil

    def generate_teacher_report(self, df_hasil):
        if df_hasil.empty:
            return pd.DataFrame()

        laporan = (
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

        total_per_guru = (
            df_hasil.groupby("ID_Guru")["Jam_Ke"]
            .count()
            .reset_index()
            .rename(columns={"Jam_Ke": "Total_JP_Mingguan"})
        )

        df_laporan = pd.merge(laporan, total_per_guru, on="ID_Guru", how="left")
        return df_laporan.sort_values(by=["ID_Guru", "Hari"]).reset_index(
            drop=True
        )


class SchedulerEngine:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df
        self.solver_instance = None

    def generate(self, timeout=180):
        self.solver_instance = SchedulerSolver(self)
        success = self.solver_instance.run_solver(
            timeout_seconds=timeout, target_max_jp=6
        )

        if not success:
            return pd.DataFrame(), pd.DataFrame()

        df_hasil = self.solver_instance.extract_results()
        df_laporan_guru = self.solver_instance.generate_teacher_report(df_hasil)

        return df_hasil, df_laporan_guru

    def export_to_excel(self, df_hasil, df_laporan_guru, filename="Hasil_Jadwal_Pelajaran.xlsx"):
        """Menyimpan hasil jadwal ke dalam file Excel dengan format rapi."""
        if df_hasil.empty:
            print("Hasil kosong, file Excel tidak dibuat.")
            return None

        # Pivot Matrix Jadwal Per Kelas (Tampilan Matriks Hari x Jam)
        pivot_jadwal = df_hasil.pivot_table(
            index=["Hari", "Jam_Ke"],
            columns="ID_Rombel",
            values="ID_Guru",
            aggfunc=lambda x: ", ".join(x),
        ).fillna("-")

        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df_hasil.to_excel(writer, sheet_name="Data_Mentah_Jadwal", index=False)
            pivot_jadwal.to_excel(writer, sheet_name="Matriks_Jadwal_Kelas")
            df_laporan_guru.to_excel(writer, sheet_name="Rekap_Beban_Guru", index=False)

        print(f"File berhasil disimpan ke {filename}")
        return filename


Scheduler = SchedulerEngine
