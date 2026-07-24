import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:
    """Class Solver Penjadwalan Sekolah menggunakan CP-SAT Constraint Programming Solver."""

    def __init__(self, scheduler_data):
        self.data = scheduler_data
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Ekstraksi Dataframe dari Session State
        self.df_guru = (
            scheduler_data.guru.copy()
            if hasattr(scheduler_data, "guru")
            else pd.DataFrame()
        )
        self.df_rombel = (
            scheduler_data.rombel.copy()
            if hasattr(scheduler_data, "rombel")
            else pd.DataFrame()
        )
        self.df_mapel = (
            scheduler_data.mapel.copy()
            if hasattr(scheduler_data, "mapel")
            else pd.DataFrame()
        )
        self.df_mengajar = (
            scheduler_data.mengajar.copy()
            if hasattr(scheduler_data, "mengajar")
            else pd.DataFrame()
        )
        self.df_slot = (
            scheduler_data.slot.copy()
            if hasattr(scheduler_data, "slot")
            else pd.DataFrame()
        )

        # Standardisasi Nama Kolom
        for df in [
            self.df_guru,
            self.df_rombel,
            self.df_mapel,
            self.df_mengajar,
            self.df_slot,
        ]:
            if not df.empty:
                df.columns = [
                    str(c).strip().replace(" ", "_") for c in df.columns
                ]

        self._preprocess_data()

    def _preprocess_data(self):
        """Memproses slot waktu harian dan pembagian blok mengajar."""
        # 1. Slot Pembelajaran
        slot_belajar = self.df_slot[
            self.df_slot["Jenis"].astype(str).str.strip().str.upper()
            == "PEMBELAJARAN"
        ].copy()
        self.list_hari = self.df_slot["Hari"].unique().tolist()

        self.jam_per_hari = {}
        self.slot_mapping = {}
        global_idx = 0

        self.day_ranges = {}
        for hari in self.list_hari:
            j_list = sorted(
                slot_belajar[slot_belajar["Hari"] == hari]["Jam"]
                .dropna()
                .astype(int)
                .tolist()
            )
            self.jam_per_hari[hari] = j_list

            start_idx = global_idx
            for jam in j_list:
                self.slot_mapping[global_idx] = (hari, jam)
                global_idx += 1
            end_idx = global_idx - 1
            if start_idx <= end_idx:
                self.day_ranges[hari] = (start_idx, end_idx)

        self.num_total_slots = global_idx

        # 2. Pemetaan MGMP Guru
        self.mgmp_guru = {}
        if "Hari_MGMP" in self.df_guru.columns:
            for _, row in self.df_guru.dropna(subset=["Hari_MGMP"]).iterrows():
                g_id = str(row.get("ID_Guru", row.get("ID_GURU", ""))).strip()
                h_mgmp = str(row["Hari_MGMP"]).strip()
                if h_mgmp in self.list_hari and g_id:
                    self.mgmp_guru[g_id] = h_mgmp

        # 3. Ekstraksi Tugas Mengajar
        mapel_col = (
            "Nama_Mapel" if "Nama_Mapel" in self.df_mapel.columns else "Mapel"
        )
        mapel_id_col = (
            "ID_Mapel" if "ID_Mapel" in self.df_mapel.columns else mapel_col
        )
        self.mapel_mapping = dict(
            zip(
                self.df_mapel[mapel_col].astype(str).str.strip().str.upper(),
                self.df_mapel[mapel_id_col],
            )
        )

        guru_col = (
            "ID_Guru" if "ID_Guru" in self.df_mengajar.columns else "Nama_Guru"
        )
        rombel_col = (
            "ID_Rombel"
            if "ID_Rombel" in self.df_mengajar.columns
            else "Kelas"
        )

        self.tugas_mengajar = []
        t_id = 0

        for _, row in self.df_mengajar.iterrows():
            guru = str(row[guru_col]).strip()
            rombel = str(row[rombel_col]).strip()
            m_nama = str(row["Mapel"]).strip()
            m_id = self.mapel_mapping.get(m_nama.upper(), m_nama)

            pembagian_str = str(row.get("Pembagian", row.get("JP", 1))).strip()
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
                except ValueError:
                    list_jp = [int(row.get("JP", 1))]

            for jp_blok in list_jp:
                if jp_blok > 0:
                    self.tugas_mengajar.append(
                        {
                            "id_tugas": t_id,
                            "guru": guru,
                            "nama_guru": row.get("Nama_Guru", guru),
                            "rombel": rombel,
                            "mapel_id": m_id,
                            "mapel_nama": m_nama,
                            "jp": jp_blok,
                        }
                    )
                    t_id += 1

    def run_solver(
        self,
        timeout_seconds=90,
        max_jam_mgmp_nongtt=0,
        max_jp_per_hari=6,
        allow_mgmp_violation=False,
    ):
        """Menjalankan engine solver CP-SAT."""
        self.model = cp_model.CpModel()

        list_guru = list(set(t["guru"] for t in self.tugas_mengajar))
        list_rombel = list(set(t["rombel"] for t in self.tugas_mengajar))

        task_intervals_rombel = {r: [] for r in list_rombel}
        task_intervals_guru = {g: [] for g in list_guru}

        self.task_vars = []
        mgmp_violations = []

        # 1. Pembuatan Variabel Keputusan (Interval Variables)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            duration = t["jp"]
            guru = t["guru"]
            rombel = t["rombel"]

            # Cari titik awal slot yang valid agar blok JP tidak terpotong beda hari
            possible_starts = []
            for hari, (d_start, d_end) in self.day_ranges.items():
                max_start = d_end - duration + 1
                for s in range(d_start, max_start + 1):
                    possible_starts.append(s)

            if not possible_starts:
                continue

            start_var = self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(possible_starts), f"start_{t_id}"
            )
            end_var = self.model.NewIntVar(
                0, self.num_total_slots, f"end_{t_id}"
            )

            # Constraint: Pembatasan Batas Hari
            for hari, (d_start, d_end) in self.day_ranges.items():
                in_day = self.model.NewBoolVar(f"in_day_{t_id}_{hari}")
                self.model.Add(start_var >= d_start).OnlyEnforceIf(in_day)
                self.model.Add(start_var <= d_end).OnlyEnforceIf(in_day)
                self.model.Add(end_var <= d_end + 1).OnlyEnforceIf(in_day)

                # Constraint MGMP Guru
                if guru in self.mgmp_guru and self.mgmp_guru[guru] == hari:
                    if not allow_mgmp_violation:
                        self.model.Add(in_day == 0)
                    else:
                        mgmp_violations.append(in_day)

            interval = self.model.NewIntervalVar(
                start_var, duration, end_var, f"interval_{t_id}"
            )

            task_intervals_rombel[rombel].append(interval)
            task_intervals_guru[guru].append(interval)

            self.task_vars.append(
                {
                    "task": t,
                    "start": start_var,
                    "end": end_var,
                }
            )

        # 2. Constraint Bebas Bentrok (No Overlap)
        for rombel, intervals in task_intervals_rombel.items():
            self.model.AddNoOverlap(intervals)

        for guru, intervals in task_intervals_guru.items():
            self.model.AddNoOverlap(intervals)

        # Soft Constraint Objective: Meminimalkan Pelanggaran MGMP jika diizinkan
        if mgmp_violations:
            self.model.Minimize(sum(mgmp_violations))

        # 3. Solver Execution Setup
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = float(timeout_seconds)
        self.solver.parameters.num_search_workers = 8

        status = self.solver.Solve(self.model)
        return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def extract_results(self):
        """Mengekstrak hasil penjadwalan menjadi DataFrame Jadwal Master."""
        results = []

        guru_name_map = {}
        if not self.df_guru.empty and "ID_Guru" in self.df_guru.columns:
            guru_name_map = dict(
                zip(self.df_guru["ID_Guru"], self.df_guru["Nama_Guru"])
            )

        for item in self.task_vars:
            t = item["task"]
            start_val = self.solver.Value(item["start"])
            duration = t["jp"]

            for slot_idx in range(start_val, start_val + duration):
                hari, jam = self.slot_mapping[slot_idx]
                guru_id = t["guru"]
                nama_guru = guru_name_map.get(guru_id, t["nama_guru"])

                results.append(
                    {
                        "Hari": hari,
                        "Jam": jam,
                        "ID_Rombel": t["rombel"],
                        "ID_Guru": guru_id,
                        "Nama_Guru": nama_guru,
                        "ID_Mapel": t["mapel_id"],
                        "Nama_Mapel": t["mapel_nama"],
                        "JP": 1,
                    }
                )

        df_res = pd.DataFrame(results)
        if not df_res.empty:
            df_res = df_res.sort_values(by=["ID_Rombel", "Hari", "Jam"])
        return df_res

    def generate_teacher_report(self, df_jadwal):
        """Membuat laporan rekapitulasi beban mengajar guru harian."""
        if df_jadwal.empty:
            return pd.DataFrame()

        report = (
            df_jadwal.groupby(["ID_Guru", "Nama_Guru", "Hari"])["JP"]
            .sum()
            .unstack(fill_value=0)
            .reset_index()
        )

        for hari in self.list_hari:
            if hari not in report.columns:
                report[hari] = 0

        cols = ["ID_Guru", "Nama_Guru"] + [
            h for h in self.list_hari if h in report.columns
        ]
        report = report[cols]
        report["Total_JP"] = report[
            [h for h in self.list_hari if h in report.columns]
        ].sum(axis=1)

        return report


def execute_scheduler_with_fallback(scheduler_data):
    """
    Fungsi Fallback Multi-Skenario:
    Mencoba menyelesaikan solver dengan melonggarkan batasan secara bertahap jika gagal.
    """
    solver = SchedulerSolver(scheduler_data)

    # Skenario 1: Strict Normal (Semua aturan & MGMP dipatuhi penuh)
    success = solver.run_solver(
        timeout_seconds=60, allow_mgmp_violation=False
    )
    if success:
        df_jadwal = solver.extract_results()
        df_laporan = solver.generate_teacher_report(df_jadwal)
        return df_jadwal, df_laporan

    # Skenario 2: Relaxation (Melonggarkan aturan hari MGMP jika jadwal terbentrok ketat)
    success = solver.run_solver(timeout_seconds=90, allow_mgmp_violation=True)
    if success:
        df_jadwal = solver.extract_results()
        df_laporan = solver.generate_teacher_report(df_jadwal)
        return df_jadwal, df_laporan

    # Jika seluruh skenario gagal
    return pd.DataFrame(), pd.DataFrame()
