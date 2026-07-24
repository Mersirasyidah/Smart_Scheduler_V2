from ortools.sat.python import cp_model
import pandas as pd

class SchedulerSolver:
    def __init__(self, assignments, days, max_hours_per_day):
        self.assignments = assignments
        self.days = days
        self.max_hours = max_hours_per_day
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

    def solve(self, mgmp_constraints=None):
        """Menyusun dan menyelesaikan constraint programming model."""
        if mgmp_constraints is None:
            mgmp_constraints = {}

        # Variables: shifts[(assignment_id, split_idx, day, start_hour)]
        variables = {}
        
        # 1. Inisialisasi Variabel Keputusan
        for assign in self.assignments:
            a_id = assign["id"]
            for s_idx, duration in enumerate(assign["splits"]):
                for day in self.days:
                    # Cek constraint MGMP Guru
                    if mgmp_constraints.get(assign["guru_id"]) == day:
                        continue # Guru sedang MGMP di hari ini

                    for hour in range(1, self.max_hours - duration + 2):
                        v_name = f"x_{a_id}_{s_idx}_{day}_{hour}"
                        variables[(a_id, s_idx, day, hour)] = self.model.NewBoolVar(v_name)

        # 2. Constraint: Setiap sub-sesi pembelajaran harus dijadwalkan TEPAT SATU KALI
        for assign in self.assignments:
            a_id = assign["id"]
            for s_idx, duration in enumerate(assign["splits"]):
                valid_slots = [
                    variables[(a_id, s_idx, day, hour)]
                    for day in self.days
                    for hour in range(1, self.max_hours - duration + 2)
                    if (a_id, s_idx, day, hour) in variables
                ]
                if valid_slots:
                    self.model.AddExactlyOne(valid_slots)

        # 3. Solve Model
        self.solver.parameters.max_time_in_seconds = 30.0
        status = self.solver.Solve(self.model)

        results = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (a_id, s_idx, day, hour), var in variables.items():
                if self.solver.Value(var) == 1:
                    assign = next(a for a in self.assignments if a["id"] == a_id)
                    duration = assign["splits"][s_idx]
                    for h in range(hour, hour + duration):
                        results.append({
                            "Hari": day,
                            "Jam": h,
                            "Kelas": assign["kelas"],
                            "Mapel": assign["mapel"],
                            "Guru": assign["guru_nama"],
                            "ID Guru": assign["guru_id"]
                        })
            return pd.DataFrame(results)
        else:
            return None
