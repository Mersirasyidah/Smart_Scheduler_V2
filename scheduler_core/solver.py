from ortools.sat.python import cp_model
import pandas as pd


class SchedulerSolver:

  def __init__(self, assignments, days, max_hours_per_day):
    self.assignments = assignments
    self.days = days
    self.max_hours = max_hours_per_day
    self.model = cp_model.CpModel()
    self.solver = cp_model.CpSolver()

  def solve(self, teachers_info=None):
    """Menyusun dan menyelesaikan constraint programming model dengan aturan bisnis lengkap.

    teachers_info: dict -> {guru_id: {'status': 'GTT'/'PERMANENT', 'mgmp_day':
    'Selasa'}}
    """
    if teachers_info is None:
      teachers_info = {}

    variables = {}

    # ---------------------------------------------------------------------
    # 1. INISIALISASI VARIABEL KEPUTUSAN & ATURAN FILTERING AWAL
    # ---------------------------------------------------------------------
    for assign in self.assignments:
      a_id = assign['id']
      guru_id = assign['guru_id']
      mapel_code = assign['mapel_code']
      kelas = assign['kelas']
      t_info = teachers_info.get(guru_id, {})

      status_guru = t_info.get('status', 'PERMANENT')
      mgmp_day = t_info.get('mgmp_day', None)

      for s_idx, duration in enumerate(assign['splits']):
        for day in self.days:
          # --- CONSTRAINT 1: ATURAN MGMP ---
          if mgmp_day == day:
            if status_guru == 'GTT':
              continue  # GTT Libur total saat MGMP
            # Non-GTT: Mengajar maksimal sampai jam ke-3.
            # Jadi jam mulai + durasi tidak boleh melebihi jam 3.

          for hour in range(1, self.max_hours - duration + 2):
            end_hour = hour + duration - 1

            # Terapkan pembatasan MGMP Non-GTT
            if mgmp_day == day and status_guru != 'GTT' and end_hour > 3:
              continue

            # --- CONSTRAINT 2: ATURAN MAPEL M11 ---
            if mapel_code == 'M11':
              if day == 'Senin':
                # Jam ideal 2-4, sisa jam maksimal ke-6
                if hour < 2 or end_hour > 6:
                  continue
              else:
                # Hari lain: Jam ideal 1-3, sisa jam maksimal ke-6
                if end_hour > 6:
                  continue

            # --- CONSTRAINT 3: ATURAN MAPEL M08 & M09 (Wajib Pagi) ---
            if mapel_code in ['M08', 'M09']:
              if end_hour > 4:  # Harus selesai di jam pagi (Maks jam 4)
                continue

            # Inisialisasi BoolVar jika lolos syarat dasar
            v_name = f'x_{a_id}_{s_idx}_{day}_{hour}'
            variables[(a_id, s_idx, day, hour)] = self.model.NewBoolVar(v_name)

    # ---------------------------------------------------------------------
    # 2. CONSTRAINT: SETIAP SUB-SESI HARUS DIJADWALKAN TEPAT SATU KALI
    # ---------------------------------------------------------------------
    for assign in self.assignments:
      a_id = assign['id']
      for s_idx, duration in enumerate(assign['splits']):
        valid_slots = [
            variables[(a_id, s_idx, day, hour)]
            for day in self.days
            for hour in range(1, self.max_hours - duration + 2)
            if (a_id, s_idx, day, hour) in variables
        ]
        if valid_slots:
          self.model.AddExactlyOne(valid_slots)
        else:
          print(
              f"⚠️ Peringatan: Tidak ada slot valid untuk Assign ID {a_id},"
              f' Sub-sesi {s_idx}'
          )
          return None

    # ---------------------------------------------------------------------
    # 3. CONSTRAINT: BEBAS BENTROK GURU & KELAS (NO OVERLAPPING)
    # ---------------------------------------------------------------------
    for day in self.days:
      for hour in range(1, self.max_hours + 1):
        # A. Tidak boleh ada 2 mapel bersamaan di kelas yang sama
        for kelas in set(a['kelas'] for a in self.assignments):
          overlapping_class_vars = []
          for (a_id, s_idx, d, h), var in variables.items():
            assign = next(a for a in self.assignments if a['id'] == a_id)
            duration = assign['splits'][s_idx]
            if d == day and assign['kelas'] == kelas and h <= hour < h + duration:
              overlapping_class_vars.append(var)
          if overlapping_class_vars:
            self.model.AddAtMostOne(overlapping_class_vars)

        # B. Tidak boleh ada Guru mengajar di 2 kelas berbeda pada jam yang sama
        for guru_id in set(a['guru_id'] for a in self.assignments):
          overlapping_teacher_vars = []
          for (a_id, s_idx, d, h), var in variables.items():
            assign = next(a for a in self.assignments if a['id'] == a_id)
            duration = assign['splits'][s_idx]
            if (
                d == day
                and assign['guru_id'] == guru_id
                and h <= hour < h + duration
            ):
              overlapping_teacher_vars.append(var)
          if overlapping_teacher_vars:
            self.model.AddAtMostOne(overlapping_teacher_vars)

    # ---------------------------------------------------------------------
    # 4. CONSTRAINT: MAKSIMAL 6 JP HARI PER GURU
    # ---------------------------------------------------------------------
    for guru_id in set(a['guru_id'] for a in self.assignments):
      for day in self.days:
        daily_teacher_hours = []
        for (a_id, s_idx, d, h), var in variables.items():
          assign = next(a for a in self.assignments if a['id'] == a_id)
          duration = assign['splits'][s_idx]
          if d == day and assign['guru_id'] == guru_id:
            # Bobot jam = variabel * durasi
            daily_teacher_hours.append(var * duration)

        if daily_teacher_hours:
          self.model.Add(sum(daily_teacher_hours) <= 6)

    # ---------------------------------------------------------------------
    # 5. CONSTRAINT KHUSUS KELAS 9: M08 & M09 HARUS SEBELUM M11
    # ---------------------------------------------------------------------
    # Mapel M08/M09 harus ditaruh pada jam yang lebih awal daripada M11
    for kelas in set(
        a['kelas'] for a in self.assignments if a['kelas'].startswith('9')
    ):
      m11_vars = [
          ((d, h), var)
          for (a_id, s_idx, d, h), var in variables.items()
          if next(
              a for a in self.assignments if a['id'] == a_id
          )['mapel_code']
          == 'M11'
          and next(a for a in self.assignments if a['id'] == a_id)['kelas']
          == kelas
      ]

      m08_m09_vars = [
          ((d, h), var)
          for (a_id, s_idx, d, h), var in variables.items()
          if next(
              a for a in self.assignments if a['id'] == a_id
          )['mapel_code']
          in ['M08', 'M09']
          and next(a for a in self.assignments if a['id'] == a_id)['kelas']
          == kelas
      ]

      # Jika kelas 9 memiliki M11 dan M08/M09
      for (d_m11, h_m11), var_m11 in m11_vars:
        for (d_early, h_early), var_early in m08_m09_vars:
          # Urutan Hari dalam indeks
          day_idx_m11 = self.days.index(d_m11)
          day_idx_early = self.days.index(d_early)

          # Jika M08/M09 dipasang pada hari/jam yang SAMA atau LEBIH AKHIR dari M11, larang kombinasi tersebut
          if (day_idx_early > day_idx_m11) or (
              day_idx_early == day_idx_m11 and h_early >= h_m11
          ):
            self.model.AddBoolOr([var_m11.Not(), var_early.Not()])

    # ---------------------------------------------------------------------
    # 6. PENYELESAIAN MODEL (SOLVE)
    # ---------------------------------------------------------------------
    self.solver.parameters.max_time_in_seconds = 60.0
    status = self.solver.Solve(self.model)

    results = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
      for (a_id, s_idx, day, hour), var in variables.items():
        if self.solver.Value(var) == 1:
          assign = next(a for a in self.assignments if a['id'] == a_id)
          duration = assign['splits'][s_idx]
          for h in range(hour, hour + duration):
            results.append({
                'Hari': day,
                'Jam': h,
                'Kelas': assign['kelas'],
                'Kode Mapel': assign['mapel_code'],
                'Mapel': assign['mapel'],
                'Guru': assign['guru_nama'],
                'ID Guru': assign['guru_id'],
            })
      return pd.DataFrame(results).sort_values(by=['Kelas', 'Hari', 'Jam'])
    else:
      return None
