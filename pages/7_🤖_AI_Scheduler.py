import pandas as pd
from ortools.sat.python import cp_model
import streamlit as st

# ==========================================
# 1. CLASS SOLVER (OR-Tools CP-SAT)
# ==========================================


class SchedulerSolver:

  def __init__(self, assignments, days, max_hours_per_day):
    self.assignments = assignments
    self.days = days
    self.max_hours = max_hours_per_day
    self.model = cp_model.CpModel()
    self.solver = cp_model.CpSolver()

  def solve(self, mgmp_constraints=None, teachers_info=None):
    """Menyusun dan menyelesaikan constraint programming model dengan aturan bisnis lengkap."""
    # Menangani ketersediaan parameter agar backward-compatible
    if teachers_info is None:
      teachers_info = mgmp_constraints if mgmp_constraints else {}

    variables = {}

    # ---------------------------------------------------------------------
    # 1. INISIALISASI VARIABEL KEPUTUSAN & ATURAN FILTERING AWAL
    # ---------------------------------------------------------------------
    for assign in self.assignments:
      a_id = assign['id']
      guru_id = assign['guru_id']
      mapel_code = assign.get('mapel_code', '')
      t_info = teachers_info.get(guru_id, {})

      # Support format dict bertingkat maupun dict sederhana
      if isinstance(t_info, dict):
        status_guru = t_info.get('status', 'PERMANENT')
        mgmp_day = t_info.get('mgmp_day', None)
      else:
        status_guru = 'PERMANENT'
        mgmp_day = t_info  # Jika t_info hanya berupa nama hari string

      for s_idx, duration in enumerate(assign['splits']):
        for day in self.days:
          # --- CONSTRAINT 1: ATURAN MGMP ---
          if mgmp_day == day:
            if status_guru == 'GTT':
              continue  # GTT Libur total saat MGMP

          for hour in range(1, self.max_hours - duration + 2):
            end_hour = hour + duration - 1

            # Non-GTT: Mengajar maksimal sampai jam ke-3 pada hari MGMP
            if mgmp_day == day and status_guru != 'GTT' and end_hour > 3:
              continue

            # --- CONSTRAINT 2: ATURAN MAPEL M11 ---
            if mapel_code == 'M11':
              if day == 'Senin':
                if hour < 2 or end_hour > 6:
                  continue
              else:
                if end_hour > 6:
                  continue

            # --- CONSTRAINT 3: ATURAN MAPEL M08 & M09 (Wajib Pagi) ---
            if mapel_code in ['M08', 'M09']:
              if end_hour > 4:
                continue

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
          st.error(
              f"Tidak ada slot waktu valid untuk Mapel {assign['mapel']} Kelas"
              f" {assign['kelas']} (ID Guru: {assign['guru_id']})."
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
    # 4. CONSTRAINT: MAKSIMAL 6 JP PER HARI PER GURU
    # ---------------------------------------------------------------------
    for guru_id in set(a['guru_id'] for a in self.assignments):
      for day in self.days:
        daily_teacher_hours = []
        for (a_id, s_idx, d, h), var in variables.items():
          assign = next(a for a in self.assignments if a['id'] == a_id)
          duration = assign['splits'][s_idx]
          if d == day and assign['guru_id'] == guru_id:
            daily_teacher_hours.append(var * duration)

        if daily_teacher_hours:
          self.model.Add(sum(daily_teacher_hours) <= 6)

    # ---------------------------------------------------------------------
    # 5. CONSTRAINT KHUSUS KELAS 9: M08 & M09 HARUS SEBELUM M11
    # ---------------------------------------------------------------------
    for kelas in set(
        a['kelas'] for a in self.assignments if a['kelas'].startswith('9')
    ):
      m11_vars = [
          ((d, h), var)
          for (a_id, s_idx, d, h), var in variables.items()
          if next(
              a for a in self.assignments if a['id'] == a_id
          ).get('mapel_code')
          == 'M11'
          and next(a for a in self.assignments if a['id'] == a_id)['kelas']
          == kelas
      ]

      m08_m09_vars = [
          ((d, h), var)
          for (a_id, s_idx, d, h), var in variables.items()
          if next(a for a in self.assignments if a['id'] == a_id).get(
              'mapel_code'
          )
          in ['M08', 'M09']
          and next(a for a in self.assignments if a['id'] == a_id)['kelas']
          == kelas
      ]

      for (d_m11, h_m11), var_m11 in m11_vars:
        for (d_early, h_early), var_early in m08_m09_vars:
          day_idx_m11 = self.days.index(d_m11)
          day_idx_early = self.days.index(d_early)

          if (day_idx_early > day_idx_m11) or (
              day_idx_early == day_idx_m11 and h_early >= h_m11
          ):
            self.model.AddBoolOr([var_m11.Not(), var_early.Not()])

    # ---------------------------------------------------------------------
    # 6. PENYELESAIAN MODEL (SOLVE)
    # ---------------------------------------------------------------------
    self.solver.parameters.max_time_in_seconds = 30.0
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
                'Mapel': assign['mapel'],
                'Kode Mapel': assign.get('mapel_code', '-'),
                'Guru': assign['guru_nama'],
                'ID Guru': assign['guru_id'],
            })
      return pd.DataFrame(results).sort_values(by=['Kelas', 'Hari', 'Jam'])
    else:
      return None


# ==========================================
# 2. ANTARMUKA STREAMLIT (UI)
# ==========================================

st.set_page_config(page_title='AI Scheduler Solver', page_icon='🤖', layout='wide')

st.title('🤖 AI Smart Scheduler Engine')
st.markdown(
    'Sistem penyusun jadwal otomatis berbasis **Constraint Programming'
    ' (OR-Tools)**.'
)

# Inisialisasi Session State jika belum ada
if 'assignments' not in st.session_state:
  # Dummy data/default untuk pengujian
  st.session_state.assignments = [
      {
          'id': 1,
          'kelas': '9A',
          'mapel_code': 'M08',
          'mapel': 'Bahasa Indonesia',
          'guru_id': 'G01',
          'guru_nama': 'Purwanto, S.Pd.',
          'splits': [2, 2],
      },
      {
          'id': 2,
          'kelas': '9A',
          'mapel_code': 'M09',
          'mapel': 'Bahasa Inggris',
          'guru_id': 'G02',
          'guru_nama': 'Asti Am Rini, S.Pd.',
          'splits': [2, 2],
      },
      {
          'id': 3,
          'kelas': '9A',
          'mapel_code': 'M11',
          'mapel': 'Matematika',
          'guru_id': 'G03',
          'guru_nama': 'Luthfan Qaedi W.',
          'splits': [3, 2],
      },
  ]

if 'teachers_info' not in st.session_state:
  st.session_state.teachers_info = {
      'G01': {'status': 'PERMANENT', 'mgmp_day': 'Selasa'},
      'G02': {'status': 'PERMANENT', 'mgmp_day': 'Rabu'},
      'G03': {'status': 'GTT', 'mgmp_day': 'Kamis'},
  }

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header('⚙️ Konfigurasi Parameter')
days = st.sidebar.multiselect(
    'Hari Sekolah',
    ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat'],
    default=['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat'],
)
max_hours = st.sidebar.number_input('Maksimal Jam ke- per Hari', 1, 10, value=9)

st.subheader('📋 Data Assignment & Status Guru')
col1, col2 = st.columns(2)

with col1:
  st.write('**Daftar Penugasan Mapel (Assignments)**')
  st.dataframe(pd.DataFrame(st.session_state.assignments), use_container_width=True)

with col2:
  st.write('**Data Guru & MGMP (Teachers Info)**')
  st.json(st.session_state.teachers_info)

st.divider()

# --- RUN SOLVER BUTTON ---
if st.button('🚀 Jalankan AI Scheduler', type='primary'):
  with st.spinner('Menyusun jadwal optimal dengan AI CP-SAT Solver...'):
    solver = SchedulerSolver(
        assignments=st.session_state.assignments,
        days=days,
        max_hours_per_day=max_hours,
    )

    # Memanggil solver dengan dua nama variabel untuk mencegah TypeError
    results_df = solver.solve(
        mgmp_constraints=st.session_state.teachers_info,
        teachers_info=st.session_state.teachers_info,
    )

  if results_df is not None and not results_df.empty:
    st.success('✅ Jadwal Berhasil Dibuat Tanpa Bentrok!')

    # Tampilkan Hasil Tipe Pivot/Tabel
    st.subheader('🗓️ Hasil Jadwal Pelajaran')

    # Filter Berdasarkan Kelas
    selected_class = st.selectbox(
        'Pilih Kelas untuk Ditampilkan:', results_df['Kelas'].unique()
    )
    class_df = results_df[results_df['Kelas'] == selected_class]

    # Format Pivot Matrix untuk Tampilan Rapi
    pivot_schedule = class_df.pivot(
        index='Jam', columns='Hari', values='Mapel'
    ).fillna('-')
    st.table(pivot_schedule)

    # Opsi Download Data Excel
    csv_data = results_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label='📥 Download CSV Hasil Jadwal',
        data=csv_data,
        file_name='hasil_jadwal_ai.csv',
        mime='text/csv',
    )
  else:
    st.error(
        '❌ Gagal menemukan kombinasi jadwal yang memenuhi semua syarat'
        ' constraint.'
    )
    st.info(
        'Saran: Periksa kembali bentrok hari MGMP atau pastikan slot jam yang'
        ' tersedia cukup untuk seluruh total jam pelajaran.'
    )
