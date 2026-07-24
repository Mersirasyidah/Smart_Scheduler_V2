import io
import pandas as pd


class ScheduleExporter:

  ALL_ROMBEL = [
      '7A',
      '7B',
      '7C',
      '7D',
      '7E',
      '8A',
      '8B',
      '8C',
      '8D',
      '8E',
      '9A',
      '9B',
      '9C',
      '9D',
      '9E',
  ]
  HARI_ORDER = ['Jumat', 'Kamis', 'Rabu', 'Selasa', 'Senin']

  @staticmethod
  def format_timetable(df_results, mapel_df=None):
    """Mengubah dataframe hasil jadwal menjadi matriks pivot (Hari & Jam vs Kelas)"""
    if df_results is None or df_results.empty:
      return pd.DataFrame()

    df = df_results.copy()

    col_hari = 'Hari' if 'Hari' in df.columns else df.columns[0]
    col_jam = (
        'Jam Ke'
        if 'Jam Ke' in df.columns
        else (
            'Jam_Ke'
            if 'Jam_Ke' in df.columns
            else ('Jam' if 'Jam' in df.columns else df.columns[1])
        )
    )
    col_rombel = (
        'Kelas / Rombel'
        if 'Kelas / Rombel' in df.columns
        else (
            'Kelas'
            if 'Kelas' in df.columns
            else ('ID_Rombel' if 'ID_Rombel' in df.columns else 'Rombel')
        )
    )
    col_val = (
        'Mata Pelajaran'
        if 'Mata Pelajaran' in df.columns
        else (
            'Mapel'
            if 'Mapel' in df.columns
            else (
                'Nama Guru'
                if 'Nama Guru' in df.columns
                else df.columns[min(3, len(df.columns) - 1)]
            )
        )
    )

    pivot_df = df.pivot_table(
        index=[col_hari, col_jam],
        columns=col_rombel,
        values=col_val,
        aggfunc=lambda x: ' / '.join(x.astype(str)),
    )

    target_cols = [c for c in ScheduleExporter.ALL_ROMBEL if c in pivot_df.columns]
    if target_cols:
      pivot_df = pivot_df.reindex(columns=ScheduleExporter.ALL_ROMBEL)

    return pivot_df.fillna('-')

  @staticmethod
  def export_to_excel(df_results, file_path='Jadwal_baru.xlsx'):
    """Mengekspor jadwal ke Excel dengan struktur persis seperti 'Jadwal baru.xlsx'

    Sheet 1: 'Jadwal_Semua_Kelas' Sheet 2-16: 'Kelas_7A' s/d 'Kelas_9E'
    """
    if df_results is None or df_results.empty:
      raise ValueError('Dataframe hasil penjadwalan kosong.')

    df = df_results.copy()

    column_mapping = {
        'Hari': 'Hari',
        'Jam': 'Jam Ke',
        'Jam_Ke': 'Jam Ke',
        'Kelas': 'Kelas / Rombel',
        'ID_Rombel': 'Kelas / Rombel',
        'Rombel': 'Kelas / Rombel',
        'Nama_Guru': 'Nama Guru',
        'Guru': 'Nama Guru',
        'Guru_Nama': 'Nama Guru',
        'Mata_Pelajaran': 'Mata Pelajaran',
        'Mapel': 'Mata Pelajaran',
        'Nama_Mapel': 'Mata Pelajaran',
    }
    df = df.rename(
        columns={k: v for k, v in column_mapping.items() if k in df.columns}
    )

    required_cols = [
        'Hari',
        'Jam Ke',
        'Kelas / Rombel',
        'Nama Guru',
        'Mata Pelajaran',
    ]
    for col in required_cols:
      if col not in df.columns:
        df[col] = '-'

    df_semua = df[required_cols].copy()

    output = io.BytesIO() if not isinstance(file_path, str) else file_path

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
      df_semua.to_excel(writer, sheet_name='Jadwal_Semua_Kelas', index=False)

      rombel_list = sorted(df_semua['Kelas / Rombel'].unique())
      target_rombels = [
          r for r in ScheduleExporter.ALL_ROMBEL if r in rombel_list
      ]
      if not target_rombels:
        target_rombels = rombel_list

      for rombel in target_rombels:
        df_kelas = df_semua[df_semua['Kelas / Rombel'] == rombel]

        pivot_kelas = df_kelas.pivot_table(
            index='Jam Ke',
            columns='Hari',
            values='Nama Guru',
            aggfunc='first',
        )

        days_present = [
            h for h in ScheduleExporter.HARI_ORDER if h in pivot_kelas.columns
        ]
        pivot_kelas = pivot_kelas.reindex(columns=days_present)
        pivot_kelas = pivot_kelas.reindex(range(1, 10))

        pivot_kelas.to_excel(writer, sheet_name=f'Kelas_{rombel}')

    if not isinstance(file_path, str):
      output.seek(0)
      return output

    return file_path
