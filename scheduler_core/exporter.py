import pandas as pd
import re

class ScheduleExporter:
    MAPEL_SHORT = {
        'Ilmu Pengetahuan Alam': 'IPA',
        'Ilmu Pengetahuan Sosial': 'IPS',
        'Pendidikan Agama Islam': 'PAI',
        'Pendidikan Agama Hindu': 'PAH',
        'Pendidikan Agama Katholik': 'PAK',
        'Pendidikan Agama Kristen': 'PAKR',
        'Bahasa Inggris': 'BIG',
        'Bahasa Indonesia': 'BIN',
        'Bahasa Jawa': 'BJW',
        'Matematika': 'MTK',
        'Informatika': 'INF',
        'Seni Budaya': 'SNB',
        'Pendidikan Jasmani Olahraga dan Kesehatan': 'PJOK',
        'Pendidikan Pancasila': 'PP',
        'Bimbingan Konseling': 'BK',
        'Prakarya': 'PRK'
    }

    @staticmethod
    def get_first_name(nama_full):
        """Mengambil kata pertama dari nama guru dan membersihkan gelar/tanda baca."""
        if pd.isna(nama_full):
            return ""
        clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
        words = clean_str.split()
        return words[0] if words else ""

    @classmethod
    def get_short_mapel(cls, mapel_full):
        """Mengubah nama mapel panjang menjadi singkatan ringkas."""
        return cls.MAPEL_SHORT.get(str(mapel_full).strip(), str(mapel_full)[:6])

    @classmethod
    def to_dataframe(cls, schedule_board):
        rows = []
        for (hari, jam), assignments in schedule_board.items():
            for item in assignments:
                nama_depan = cls.get_first_name(item['nama_guru'])
                mapel_singkat = cls.get_short_mapel(item['mapel'])
                rows.append({
                    'Hari': hari,
                    'Jam': jam,
                    'Kelas': item['kelas'],
                    'ID Guru': item['guru_id'],
                    'Nama Guru Full': item['nama_guru'],
                    'Nama Guru': nama_depan,
                    'Mapel Full': item['mapel'],
                    'Mapel': mapel_singkat
                })
        return pd.DataFrame(rows)

    @classmethod
    def create_class_matrix(cls, df_results):
        """Membuat matriks ringkas per kelas (Format: IPA (Purwanto))."""
        if df_results.empty:
            return pd.DataFrame()
            
        df_results['Matkul_Guru'] = df_results['Mapel'] + " (" + df_results['Nama Guru'] + ")"
        matrix = df_results.pivot_table(
            index=['Hari', 'Jam'],
            columns='Kelas',
            values='Matkul_Guru',
            aggfunc='first'
        ).fillna('-')
        return matrix
