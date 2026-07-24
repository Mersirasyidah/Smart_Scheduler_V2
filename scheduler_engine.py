import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:
    """CP-SAT Solver Engine untuk Penjadwalan Sekolah Otomatis."""

    def __init__(self, data_master):
        self.data = data_master
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.assignments = {}
        self.status = None

    def run_solver(
        self, timeout_seconds=90, max_jam_mgmp_nongtt=4, max_jp_per_hari=6
    ):
        """Menjalankan pencarian solusi jadwal KBM dengan constraint CP-SAT."""
        self.model = cp_model.CpModel()
        self.assignments = {}

        # Ambil data master secara fleksibel
        guru_df = getattr(self.data, "guru", pd.DataFrame())
        rombel_df = getattr(self.data, "rombel", pd.DataFrame())
        slot_df = getattr(self.data, "slot", pd.DataFrame())
        mengajar_df = getattr(self.data, "mengajar", pd.DataFrame())

        if mengajar_df.empty or slot_df.empty:
            return False

        # Preprocessing ID
        col_rombel = "ID_Rombel" if "ID_Rombel" in rombel_df.columns else "Kelas"
        col_mengajar_rombel = (
            "ID_Rombel" if "ID_Rombel" in mengajar_df.columns else "Kelas"
        )

        # Inisialisasi Variabel Keputusan: X[tugas_idx, slot_idx]
        for t_idx, tugas in mengajar_df.iterrows():
            for s_idx, slot in slot_df.iterrows():
                self.assignments[(t_idx, s_idx)] = self.model.NewBoolVar(
                    f"x_{t_idx}_{s_idx}"
                )

        # Constraint 1: Pemenuhan total JP tiap tugas mengajar
        for t_idx, tugas in mengajar_df.iterrows():
            jp_butuh = int(tugas.get("JP", 1))
            self.model.Add(
                sum(
                    self.assignments[(t_idx, s_idx)]
                    for s_idx in slot_df.index
                )
                == jp_butuh
            )

        # Constraint 2: Mencegah Bentrok Rombel
        for s_idx in slot_df.index:
            for r_id in rombel_df[col_rombel].unique():
                tugas_rombel = mengajar_df[
                    mengajar_df[col_mengajar_rombel] == r_id
                ].index
                if len(tugas_rombel) > 0:
                    self.model.Add(
                        sum(
                            self.assignments[(t_idx, s_idx)]
                            for t_idx in tugas_rombel
                        )
                        <= 1
                    )

        # Constraint 3: Mencegah Bentrok Guru
        for s_idx in slot_df.index:
            for g_id in guru_df["ID_Guru"].unique():
                tugas_guru = mengajar_df[
                    mengajar_df["ID_Guru"] == g_id
                ].index
                if len(tugas_guru) > 0:
                    self.model.Add(
                        sum(
                            self.assignments[(t_idx, s_idx)]
                            for t_idx in tugas_guru
                        )
                        <= 1
                    )

        # Set Parameter Solver
        self.solver.parameters.max_time_in_seconds = float(timeout_seconds)
        self.solver.parameters.num_search_workers = 4
        self.status = self.solver.Solve(self.model)

        return self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def extract_results(self):
        """Mengekstrak hasil dari solver ke dalam bentuk DataFrame."""
        if self.status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return pd.DataFrame()

        slot_df = getattr(self.data, "slot", pd.DataFrame())
        mengajar_df = getattr(self.data, "mengajar", pd.DataFrame())

        results = []
        for (t_idx, s_idx), var in self.assignments.items():
            if self.solver.Value(var) == 1:
                tugas = mengajar_df.loc[t_idx]
                slot = slot_df.loc[s_idx]

                rombel_val = tugas.get(
                    "ID_Rombel", tugas.get("Kelas", "Rombel")
                )
                jam_val = slot.get("Jam_Ke", slot.get("Jam", "1"))

                results.append(
                    {
                        "Hari": slot.get("Hari", "-"),
                        "Jam_Ke": jam_val,
                        "ID_Rombel": rombel_val,
                        "ID_Guru": tugas.get("ID_Guru", "-"),
                        "ID_Mapel": tugas.get("ID_Mapel", "-"),
                    }
                )

        df_res = pd.DataFrame(results)
        if not df_res.empty and "Hari" in df_res.columns:
            df_res = df_res.sort_values(by=["Hari", "Jam_Ke"]).reset_index(
                drop=True
            )
        return df_res

    def generate_teacher_report(self, df_results):
        """Membuat laporan rekapitulasi jam mengajar guru."""
        if df_results is None or df_results.empty:
            return pd.DataFrame()

        rekap = (
            df_results.groupby(["ID_Guru", "ID_Mapel"])
            .size()
            .reset_index(name="Total_JP_Terjadwal")
        )
        return rekap


def execute_scheduler_with_fallback(scheduler_data):
    """Fungsi pembantu untuk mencoba eksekusi dengan beberapa skenario pelonggaran constraint."""
    solver = SchedulerSolver(scheduler_data)

    # Skenario 1: Strict
    if solver.run_solver(
        timeout_seconds=60, max_jam_mgmp_nongtt=4, max_jp_per_hari=6
    ):
        df_j = solver.extract_results()
        return df_j, solver.generate_teacher_report(df_j)

    # Skenario 2: Medium
    if solver.run_solver(
        timeout_seconds=90, max_jam_mgmp_nongtt=6, max_jp_per_hari=8
    ):
        df_j = solver.extract_results()
        return df_j, solver.generate_teacher_report(df_j)

    # Skenario 3: Relaxed
    if solver.run_solver(
        timeout_seconds=120, max_jam_mgmp_nongtt=8, max_jp_per_hari=10
    ):
        df_j = solver.extract_results()
        return df_j, solver.generate_teacher_report(df_j)

    return pd.DataFrame(), pd.DataFrame()
