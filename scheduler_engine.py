import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:
    """CP-SAT Solver Engine untuk Penjadwalan Sekolah Automatis."""

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

        # 1. Ambil data master
        guru_df = getattr(self.data, "guru", pd.DataFrame())
        rombel_df = getattr(self.data, "rombel", pd.DataFrame())
        slot_df = getattr(self.data, "slot", pd.DataFrame())
        mengajar_df = getattr(self.data, "mengajar", pd.DataFrame())

        if mengajar_df.empty or slot_df.empty:
            return False

        # Prepare Decision Variables: X[tugas_idx, slot_idx]
        for t_idx, tugas in mengajar_df.iterrows():
            jp_butuh = int(tugas.get("JP", 1))
            for s_idx, slot in slot_df.iterrows():
                var_name = f"x_{t_idx}_{s_idx}"
                self.assignments[(t_idx, s_idx)] = self.model.NewBoolVar(
                    var_name
                )

        # Constraint 1: Setiap alokasi mengajar harus terpenuhi total JP-nya
        for t_idx, tugas in mengajar_df.iterrows():
            jp_butuh = int(tugas.get("JP", 1))
            self.model.Add(
                sum(
                    self.assignments[(t_idx, s_idx)]
                    for s_idx in slot_df.index
                )
                == jp_butuh
            )

        # Constraint 2: Rombel tidak boleh bentrok di slot jam yang sama
        for s_idx in slot_df.index:
            for rombel_id in rombel_df["ID_Rombel"].unique():
                tugas_rombel = mengajar_df[
                    mengajar_df["ID_Rombel"] == rombel_id
                ].index
                if len(tugas_rombel) > 0:
                    self.model.Add(
                        sum(
                            self.assignments[(t_idx, s_idx)]
                            for t_idx in tugas_rombel
                        )
                        <= 1
                    )

        # Constraint 3: Guru tidak boleh bentrok di slot jam yang sama
        for s_idx in slot_df.index:
            for guru_id in guru_df["ID_Guru"].unique():
                tugas_guru = mengajar_df[
                    mengajar_df["ID_Guru"] == guru_id
                ].index
                if len(tugas_guru) > 0:
                    self.model.Add(
                        sum(
                            self.assignments[(t_idx, s_idx)]
                            for t_idx in tugas_guru
                        )
                        <= 1
                    )

        # Set Solver Parameters
        self.solver.parameters.max_time_in_seconds = float(timeout_seconds)
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

                results.append(
                    {
                        "Hari": slot.get("Hari", "-"),
                        "Jam_Ke": slot.get("Jam_Ke", slot.get("Jam", "-")),
                        "ID_Rombel": tugas.get(
                            "ID_Rombel", tugas.get("Kelas", "-")
                        ),
                        "ID_Guru": tugas.get("ID_Guru", "-"),
                        "ID_Mapel": tugas.get("ID_Mapel", "-"),
                    }
                )

        df_res = pd.DataFrame(results)
        if not df_res.empty and "Hari" in df_res.columns:
            df_res = df_res.sort_values(by=["Hari", "Jam_Ke"])
        return df_res

    def generate_teacher_report(self, df_results):
        """Membuat laporan total jam mengajar per guru."""
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

    # Skenario 1: Strict (Timeout 60 detik, Max JP 6)
    success = solver.run_solver(
        timeout_seconds=60, max_jam_mgmp_nongtt=4, max_jp_per_hari=6
    )
    if success:
        df_jadwal = solver.extract_results()
        df_laporan = solver.generate_teacher_report(df_jadwal)
        return df_jadwal, df_laporan

    # Skenario 2: Medium (Timeout 90 detik, Max JP 8)
    success = solver.run_solver(
        timeout_seconds=90, max_jam_mgmp_nongtt=6, max_jp_per_hari=8
    )
    if success:
        df_jadwal = solver.extract_results()
        df_laporan = solver.generate_teacher_report(df_jadwal)
        return df_jadwal, df_laporan

    # Skenario 3: Relaxed (Timeout 120 detik)
    success = solver.run_solver(
        timeout_seconds=120, max_jam_mgmp_nongtt=8, max_jp_per_hari=10
    )
    if success:
        df_jadwal = solver.extract_results()
        df_laporan = solver.generate_teacher_report(df_jadwal)
        return df_jadwal, df_laporan

    return pd.DataFrame(), pd.DataFrame()
