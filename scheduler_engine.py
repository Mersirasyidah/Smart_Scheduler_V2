import io
import pandas as pd
from ortools.sat.python import cp_model


# =====================================================================
# 1. CLASS SOLVER (CP-SAT ENGINE)
# =====================================================================
class SchedulerSolver:

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.model = cp_model.CpModel()
        self.solver = None

        # Standardisasi Data & DataFrame
        self.guru = scheduler.guru.copy()
        self.rombel = scheduler.rombel.copy()
        self.mengajar = scheduler.mengajar.copy()
        self.mapel = scheduler.mapel.copy()
        self.slot = scheduler.slot.copy()

        for df in [self.guru, self.rombel, self.mengajar, self.mapel, self.slot]:
            df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]

        # Sanitasi String & Ekstraksi List
        self.list_guru = self.guru["ID_Guru"].astype(str).str.strip().tolist()

        col_rombel = "Kelas" if "Kelas" in self.rombel.columns else "ID_Rombel"
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

        # Ekstraksi Tugas Mengajar
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
                    int(x)
                    for x in pembagian_str.split(",")
                    if x.strip().isdigit()
                ]
            elif "." in pembagian_str:
                list_jp = [
                    int(x)
                    for x in pembagian_str.split(".")
                    if x.strip().isdigit()
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
            if (
                kode in ["M11", "PJOK"]
                or "JASMANI" in nama
                or "PENJAS" in nama
            ):
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

            if "GTT" in status_str or "HONOR" in status_str or "G33" in g_id:
                self.guru_gtt_set.add(g_id)

            for col_mgmp in ["Hari_MGMP", "Hari_Libur", "Libur", "MGMP"]:
                if col_mgmp in row and pd.notna(row[col_mgmp]):
                    val = str(row[col_mgmp]).strip()
                    if val and val.lower() != "nan" and val != "-":
                        self.guru_mgmp_dict[g_id] = val
                        break

        self.variables = {}
        self.penalties = []

    def run_solver(
        self,
        timeout_seconds=120,
        max_jam_mgmp_nongtt=4,
        max_jp_per_hari=6,
    ):
        self.model = cp_model.CpModel()
        self.variables = {}
        self.penalties = []

        # Variabel Keputusan
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari.get(hari, []):
                    self.variables[(t_id, hari, jam)] = (
                        self.model.NewBoolVar(f"t_{t_id}_{hari}_{jam}")
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

        kamis_key = next(
            (h for h in self.list_hari if h.lower() == "kamis"), None
        )

        # Constraints Dasar & Preferensi Mapel
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            guru = t["guru"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            # Pemenuhan JP
            self.model.Add(
                sum(
                    self.variables[(t_id, hari, jam)]
                    for hari in self.list_hari
                    for jam in self.jam_per_hari.get(hari, [])
                )
                == t["jp"]
            )

            # 1 Blok Hari per Tugas
            self.model.Add(
                sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari)
                == 1
            )

            # Soft Constraint: Agama M01
            if mapel == "M01" and kamis_key:
                if rombel in ["7A", "8A", "8C", "9A"]:
                    self.penalties.append(
                        (1 - tugas_hari_aktif[(t_id, kamis_key)]) * 500
                    )

            # Soft Constraint: Guru G32
            if guru == "G32" and kamis_key and rombel == "8B":
                self.penalties.append(
                    (1 - tugas_hari_aktif[(t_id, kamis_key)]) * 500
                )

            # Hard Constraint: PJOK Max Jam ke-6
            if mapel in self.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari.get(hari, []):
                        if (t_id, hari, jam) in self.variables:
                            if jam > 6:
                                self.model.Add(
                                    self.variables[(t_id, hari, jam)] == 0
                                )

        # Constraints MGMP (GTT vs Non-GTT)
        for guru, hari_libur in self.guru_mgmp_dict.items():
            target_hari = next(
                (h for h in self.list_hari if h.lower() == hari_libur.lower()),
                None,
            )
            if target_hari:
                tugas_guru = [
                    t["id_tugas"]
                    for t in self.tugas_mengajar
                    if t["guru"] == guru
                ]
                is_gtt = guru in self.guru_gtt_set

                for t_id in tugas_guru:
                    for jam in self.jam_per_hari.get(target_hari, []):
                        if (t_id, target_hari, jam) in self.variables:
                            if is_gtt:
                                # GTT: Libur Full (0 JP)
                                self.model.Add(
                                    self.variables[(t_id, target_hari, jam)]
                                    == 0
                                )
                            else:
                                # Non-GTT: Mengajar hanya sampai Jam ke-N
                                if jam > max_jam_mgmp_nongtt:
                                    self.model.Add(
                                        self.variables[
                                            (t_id, target_hari, jam)
                                        ]
                                        == 0
                                    )

        # Max JP Guru per Hari
        for guru in self.list_guru:
            tugas_guru = [
                t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
            ]
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
                        <= max_jp_per_hari
                    )

        # Mencegah Bentrok Rombel
        for rombel in self.list_rombel:
            tugas_rombel = [
                t["id_tugas"]
                for t in self.tugas_mengajar
                if t["rombel"] == rombel
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

        # Mencegah Bentrok Guru
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

        # Jam Berurutan (Sliding Window)
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
                            s_var = self.model.NewBoolVar(
                                f"start_{t_id}_{hari}_{jam_hari[i]}"
                            )
                            start_vars.append(s_var)
                            for offset in range(target_jp):
                                j_target = jam_hari[i + offset]
                                if (t_id, hari, j_target) in self.variables:
                                    self.model.Add(
                                        self.variables[(t_id, hari, j_target)]
                                        == 1
                                    ).OnlyEnforceIf(s_var)
                        self.model.Add(
                            sum(start_vars) == tugas_hari_aktif[(t_id, hari)]
                        )
                    else:
                        self.model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

        if self.penalties:
            self.model.Minimize(sum(self.penalties))

        # Solve
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


# =====================================================================
# 2. WRAPPER CLASS UNTUK PENGGUNAAN DI STREAMLIT
# =====================================================================
class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru = guru_df
        self.rombel = rombel_df
        self.mengajar = mengajar_df
        self.mapel = mapel_df
        self.slot = slot_df

    def solve_with_fallback(self, timeout_total=120, progress_callback=None):
        """Mencoba berbagai skenario secara bertahap hingga menemukan solusi yang feasible."""
        skenario_list = [
            {
                "desc": "Ideal: Max 6 JP/Hari | MGMP Non-GTT Max Jam Ke-4",
                "max_jp": 6,
                "max_mgmp": 4,
            },
            {
                "desc": "Relaksasi 1: Max 6 JP/Hari | MGMP Non-GTT Max Jam Ke-3",
                "max_jp": 6,
                "max_mgmp": 3,
            },
            {
                "desc": "Relaksasi 2: Max 7 JP/Hari | MGMP Non-GTT Max Jam Ke-4",
                "max_jp": 7,
                "max_mgmp": 4,
            },
            {
                "desc": "Darurat: Max 8 JP/Hari | MGMP Non-GTT Max Jam Ke-5",
                "max_jp": 8,
                "max_mgmp": 5,
            },
        ]

        timeout_per_skenario = max(10, timeout_total // len(skenario_list))

        for i, skenario in enumerate(skenario_list, start=1):
            if progress_callback:
                progress_callback(
                    f"Mencoba Skenario {i}/{len(skenario_list)}: {skenario['desc']}..."
                )

            solver = SchedulerSolver(self)
            is_success = solver.run_solver(
                timeout_seconds=timeout_per_skenario,
                max_jam_mgmp_nongtt=skenario["max_mgmp"],
                max_jp_per_hari=skenario["max_jp"],
            )

            if is_success:
                df_hasil = solver.extract_results()
                df_laporan = solver.generate_teacher_report(df_hasil)
                return True, df_hasil, df_laporan, skenario["desc"]

        return False, pd.DataFrame(), pd.DataFrame(), "Semua Skenario Gagal"
