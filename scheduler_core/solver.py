# scheduler_core/solver.py

import pandas as pd
from ortools.sat.python import cp_model
from scheduler_core.constraints import ConstraintBuilder


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

        for df in [
            self.guru,
            self.rombel,
            self.mengajar,
            self.mapel,
            self.slot,
        ]:
            df.columns = [c.replace(" ", "_") for c in df.columns]

        self.list_guru = self.guru["ID_Guru"].astype(str).str.strip().tolist()
        self.list_rombel = (
            self.rombel["Kelas"].astype(str).str.strip().tolist()
            if "Kelas" in self.rombel.columns
            else self.rombel["ID_Rombel"].astype(str).str.strip().tolist()
        )
        self.list_mapel = (
            self.mapel["ID_Mapel"].astype(str).str.strip().tolist()
        )
        self.list_hari = self.slot["Hari"].unique().tolist()

        slot_belajar = self.slot[
            self.slot["Jenis"].str.upper() == "PEMBELAJARAN"
        ]
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
            zip(
                self.mapel["Nama_Mapel"].str.strip().str.upper(),
                self.mapel["ID_Mapel"].astype(str).str.strip(),
            )
        )

        for _, row in self.mengajar.iterrows():
            guru = str(row["ID_Guru"]).strip()
            rombel = (
                str(row["Kelas"]).strip()
                if "Kelas" in self.mengajar.columns
                else str(row["ID_Rombel"]).strip()
            )
            mapel_nama = str(row["Mapel"]).strip().upper()
            mapel_id = mapel_mapping.get(
                mapel_nama, str(row.get("ID_Mapel", "M99")).strip()
            )

            pembagian_str = str(row["Pembagian"]).strip()
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
                    list_jp = [int(row["JP"])]

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
        self.tugas_hari_aktif = {}
        self.penalties = []

    def run_solver(self, timeout_seconds=120, max_jam_mgmp_nongtt=3):
        # Inisialisasi Variabel Utama
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.variables[(t_id, hari, jam)] = (
                        self.model.NewBoolVar(f"t_{t_id}_{hari}_{jam}")
                    )

        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                self.tugas_hari_aktif[(t_id, hari)] = self.model.NewBoolVar(
                    f"aktif_t_{t_id}_{hari}"
                )
                self.model.AddMaxEquality(
                    self.tugas_hari_aktif[(t_id, hari)],
                    [
                        self.variables[(t_id, hari, jam)]
                        for jam in self.jam_per_hari[hari]
                    ],
                )

        # Menerapkan Semua Constraint via ConstraintBuilder
        builder = ConstraintBuilder(self)
        builder.apply_all(max_jam_mgmp_nongtt=max_jam_mgmp_nongtt)

        # Minimalkan Total Penalti jika ada
        if self.penalties:
            self.model.Minimize(sum(self.penalties))

        # Eksekusi CP-SAT Solver
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
