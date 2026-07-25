import pandas as pd

class ScheduleExporter:
    @staticmethod
    def to_dataframe(schedule_board):
        rows = []
        for (hari, jam), assignments in schedule_board.items():
            for item in assignments:
                rows.append({
                    'Hari': hari,
                    'Jam': jam,
                    'Kelas': item['kelas'],
                    'ID Guru': item['guru_id'],
                    'Nama Guru': item['nama_guru'],
                    'Mapel': item['mapel']
                })
        return pd.DataFrame(rows)

    @staticmethod
    def create_class_matrix(df_results):
        """Membuat matriks jadwal per kelas (Hari & Jam vs Kelas)."""
        if df_results.empty:
            return pd.DataFrame()
            
        df_results['Matkul_Guru'] = df_results['Mapel'] + "\n(" + df_results['Nama Guru'] + ")"
        matrix = df_results.pivot_table(
            index=['Hari', 'Jam'],
            columns='Kelas',
            values='Matkul_Guru',
            aggfunc='first'
        ).fillna('-')
        return matrix
