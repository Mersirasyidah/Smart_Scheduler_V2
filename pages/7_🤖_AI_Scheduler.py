import pandas as pd
# 1. Import Streamlit
import streamlit as st

# 2. Wajib paling atas sebelum elemen UI Streamlit / OR-Tools lainnya
st.set_page_config(
    page_title='AI Scheduler Engine', page_icon='🤖', layout='wide'
)

from ortools.sat.python import cp_model


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
    if teachers_info is None:
      teachers_info = mgmp_constraints if mgmp_constraints else {}

    variables = {}

    # --- 1. INISIALISASI VARIABEL & FILTERING ATURAN ---
    for assign in self.assignments:
      a_id = assign['id']
      guru_id = assign['guru_id']
      mapel_code = assign.get('mapel_code', '')
      t_info = teachers_info.get(guru_id, {})

      if isinstance(t_info, dict):
        status_guru = t_info.get('status', 'PERMANENT')
        mgmp_day = t_info.get('mgmp_day', None)
      else:
        status_guru = 'PERMANENT'
        mgmp_day = t_info

      for s_idx, duration in enumerate(assign['splits']):
        for day in self.days:
          # Constraint MGMP: GTT Libur Total
          if mgmp_day == day and status_guru == 'GTT':
            continue

          for hour in range(1, self.max_hours - duration + 2):
            end_hour = hour + duration - 1

            # Constraint MGMP: Non-GTT Maksimal Jam ke-3
            if mgmp_day == day and status_guru != 'GTT' and end_hour > 3:
              continue

            # Constraint M11
            if mapel_code == 'M11':
              if day == 'Senin' and (hour < 2 or end_hour > 6):
                continue
              elif day != 'Senin' and end_hour > 6:
                continue

            # Constraint M08 & M09 (Wajib Pagi)
            if mapel_code in ['M08', 'M09'] and end_hour > 4:
              continue

            v_name = f'x_{a_id}_{s_idx}_{day}_{hour}'
            variables[(a_id, s_idx, day, hour)] = self.model.NewBoolVar(v_name)

    # --- 2. CONSTRAINT: TEPAT 1 SESI ---
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
              f"Tidak ada slot valid untuk {assign['mapel']} Kelas"
              f" {assign['kelas']}"
          )
          return None

    # --- 3. CONSTRAINT: BEBAS BENTROK KELAS & GURU ---
    for day in self.days:
      for hour in range(1, self.max_hours + 1):
        for kelas in set(a['kelas'] for a in self.assignments):
          overlapping_class_vars = [
              var
              for (a_id, s_idx, d, h), var in variables.items()
              if d == day
              and next(a for a in self.assignments if a['id'] == a_id)['kelas']
              == kelas
              and h
              <= hour
              < h + next(a for a in self.assignments if a['id'] == a_id)['splits'][s_idx]
          ]
          if overlapping_class_vars:
            self.model.AddAtMostOne(overlapping_class_vars)

        for guru_id in set(a['guru_id'] for a in self.assignments):
          overlapping_teacher_vars = [
              var
              for (a_id, s_idx, d, h), var in variables.items()
              if d == day
              and next(a for a in self.assignments if a['id'] == a_id)[
                  'guru_id'
              ]
              == guru_id
              and h
              <= hour
              < h + next(a for a in self.assignments if a['id'] == a_id)['splits'][s_idx]
          ]
          if overlapping_teacher_vars:
            self.model.AddAtMostOne(overlapping_teacher_vars)

    # --- 4. CONSTRAINT: MAKS 6 JP HARI PER GURU ---
    for guru_id in set(a['guru_id'] for a in self.assignments):
      for day in self.days:
        daily_hours = [
            var
            * next(a for a in self.assignments if a['id'] == a_id)['splits'][
                s_idx
            ]
            for (a_id, s_idx, d, h), var in variables.items()
            if d == day
            and next(a for a in self.assignments if a['id'] == a_id)['guru_id']
            == guru_id
        ]
        if daily_hours:
          self.model.Add(sum(daily_hours) <= 6)

    # --- 5. CONSTRAINT KELAS 9: M08 & M09 SEBELUM M11 ---
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
      m_early_vars = [
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
        for (d_e, h_e), var_e in m_early_vars:
          if (self.days.index(d_e) > self.days.index(d_m11)) or (
              d_e == d_m11 and h_e >= h_m11
          ):
            self.model.AddBoolOr([var_m11.Not(), var_e.Not()])

    # --- 6. SOLVE MODEL ---
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
                'Kode Mapel': assign.get('mapel_code', '-'),
                'Mapel': assign['mapel'],
                'Guru': assign['guru_nama'],
                'ID Guru': assign['guru_id'],
            })
      return pd.DataFrame(results).sort_values(by=['Kelas', 'Hari', 'Jam'])
    return None


# ==========================================
# 2. UI STREAMLIT & LAPORAN SEMUA KELAS
# ==========================================

st.title('🤖 AI Smart Scheduler Engine')
st.markdown(
    'Sistem penyusun jadwal otomatis berbasis **Constraint Programming'
    ' (OR-Tools)**.'
)

# Dummy Data State
if 'assignments' not in st.session_state:
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
      {
          'id': 4,
          'kelas': '8A',
          'mapel_code': 'M08',
          'mapel': 'Bahasa Indonesia',
          'guru_id': 'G01',
          'guru_nama': 'Purwanto, S.Pd.',
          'splits': [2, 2],
      },
      {
          'id': 5,
          'kelas': '8A',
          'mapel_code': 'M11',
          'mapel': 'Matematika',
          'guru_id': 'G04',
          'guru_nama': 'Anggi Supriyadi, S.Hum',
          'splits': [3, 2],
      },
  ]

if 'teachers_info' not in st.session_state:
  st.session_state.teachers_info = {
      'G01': {'status': 'PERMANENT', 'mgmp_day': 'Selasa'},
      'G02': {'status': 'PERMANENT', 'mgmp_day': 'Rabu'},
      'G03': {'status': 'GTT', 'mgmp_day': 'Kamis'},
      'G04': {'status': 'GTT', 'mgmp_day': 'Jumat'},
  }

# Sidebar
st.sidebar.header('⚙️ Konfigurasi Parameter')
days = st.sidebar.multiselect(
    'Hari Sekolah',
    ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat'],
    default=['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat'],
)
max_hours = st.sidebar.number_input('Maksimal Jam ke- per Hari', 1, 10, value=9)

# Run Solver Button
if st.button('🚀 Generate Laporan Jadwal Semua Kelas', type='primary'):
  with st.spinner('Menyusun dan mengoptimalkan jadwal seluruh kelas...'):
    solver = SchedulerSolver(
        assignments=st.session_state.assignments,
        days=days,
        max_hours_per_day=max_hours,
    )
    results_df = solver.solve(
        mgmp_constraints=st.session_state.teachers_info,
        teachers_info=st.session_state.teachers_info,
    )

  if results_df is not None and not results_df.empty:
    st.success('✅ Jadwal Seluruh Kelas Berhasil Disusun Lengkap!')
    results_df['Display'] = (
        results_df['Kode Mapel'] + ' (' + results_df['Guru'] + ')'
    )

    st.header('📊 LAPORAN JADWAL PELAJARAN SEMUA KELAS')

    tab1, tab2, tab3 = st.tabs([
        '🗓️ Laporan Master (Semua Kelas)',
        '🏫 Laporan per Kelas',
        '📄 Data Mentah / Export',
    ])

    with tab1:
      for day in days:
        st.markdown(f'### 📌 Hari: {day.upper()}')
        df_day = results_df[results_df['Hari'] == day]
        if not df_day.empty:
          pivot_day = df_day.pivot(
              index='Jam', columns='Kelas', values='Display'
          ).fillna('-')
          st.table(pivot_day)
        else:
          st.info(f'Tidak ada kegiatan KBM di hari {day}.')
        st.divider()

    with tab2:
      all_classes = sorted(results_df['Kelas'].unique())
      class_tabs = st.tabs([f'Kelas {c}' for c in all_classes])
      for idx, c_name in enumerate(all_classes):
        with class_tabs[idx]:
          df_class = results_df[results_df['Kelas'] == c_name]
          pivot_class = df_class.pivot(
              index='Jam', columns='Hari', values='Display'
          ).fillna('-')
          existing_days = [d for d in days if d in pivot_class.columns]
          pivot_class = pivot_class[existing_days]
          st.markdown(f'#### 🎓 Jadwal Pelajaran Kelas **{c_name}**')
          st.table(pivot_class)

    with tab3:
      st.dataframe(
          results_df[
              ['Hari', 'Jam', 'Kelas', 'Kode Mapel', 'Mapel', 'Guru']
          ],
          use_container_width=True,
      )
      csv_data = results_df.to_csv(index=False).encode('utf-8')
      st.download_button(
          label='📥 Download CSV Laporan Jadwal',
          data=csv_data,
          file_name='laporan_jadwal_semua_kelas.csv',
          mime='text/csv',
      )
  else:
    st.error('❌ Gagal membuat jadwal. Periksa kembali ketersediaan slot jam.')
