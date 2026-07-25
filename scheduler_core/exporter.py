import pandas as pd
import re

class ScheduleExporter:
    MAPEL_TO_KODE = {
        'Pendidikan Agama Islam': 'M01',
        'Pendidikan Agama Hindu': 'M02',
        'Pendidikan Agama Katholik': 'M03',
        'Pendidikan Agama Kristen': 'M04',
        'Pendidikan Pancasila': 'M05',
        'Bahasa Indonesia': 'M06',
        'Matematika': 'M07',
        'Ilmu Pengetahuan Alam': 'M08',
        'Ilmu Pengetahuan Sosial': 'M09',
        'Bahasa Inggris': 'M10',
        'Pendidikan Jasmani Olahraga dan Kesehatan': 'M11',
        'Informatika': 'M12',
        'Seni Budaya': 'M13',
        'Prakarya': 'M14',
        'Bahasa Jawa': 'M15',
        'Bimbingan Konseling': 'M16'
    }

    MAPEL_SHORT = {
        'Pendidikan Agama Islam': 'PAI',
        'Pendidikan Pancasila': 'PP',
        'Bahasa Indonesia': 'BIN',
        'Matematika': 'MTK',
        'Ilmu Pengetahuan Alam': 'IPA',
        'Ilmu Pengetahuan Sosial': 'IPS',
        'Bahasa Inggris': 'BIG',
        'Pendidikan Jasmani Olahraga dan Kesehatan': 'PJOK',
        'Informatika': 'INF',
        'Seni Budaya': 'SNB',
        'Prakarya': 'PRK',
        'Bahasa Jawa': 'BJW',
        'Bimbingan Konseling': 'BK'
    }

    @staticmethod
    def get_first_name(nama_full):
        if pd.isna(nama_full):
            return ""
        clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
        words = clean_str.split()
        return words[0] if words else ""

    @classmethod
    def get_kode_mapel(cls, mapel_full):
        return cls.MAPEL_TO_KODE.get(str(mapel_full).strip(), 'MXX')

    @classmethod
    def get_short_mapel(cls, mapel_full):
        return cls.MAPEL_SHORT.get(str(mapel_full).strip(), str(mapel_full)[:4])

    @classmethod
    def to_dataframe(cls, schedule_board):
        rows = []
        for (hari, jam), assignments in schedule_board.items():
            for item in assignments:
                nama_depan = cls.get_first_name(item['nama_guru'])
                mapel_singkat = cls.get_short_mapel(item['mapel'])
                kode_mapel = cls.get_kode_mapel(item['mapel'])
                
                rows.append({
                    'Hari': hari,
                    'Jam': jam,
                    'Kelas': item['kelas'],
                    'ID Guru': item['guru_id'],
                    'Nama Guru Full': item['nama_guru'],
                    'Nama Guru': nama_depan,
                    'Mapel Full': item['mapel'],
                    'Mapel Singkat': mapel_singkat,
                    'Kode Mapel': kode_mapel
                })
        return pd.DataFrame(rows)

    @classmethod
    def create_class_matrix_by_name(cls, df_results):
        """TAMPILAN 1: Menggunakan Nama Depan Guru & Singkatan Mapel -> Contoh: IPA (Purwanto)"""
        if df_results.empty:
            return pd.DataFrame()
            
        df_results['Display_Name'] = df_results['Mapel Singkat'] + "\n(" + df_results['Nama Guru'] + ")"
        matrix = df_results.pivot_table(
            index=['Hari', 'Jam'],
            columns='Kelas',
            values='Display_Name',
            aggfunc='first'
        ).fillna('-')
        return matrix

    @classmethod
    def create_class_matrix_by_code(cls, df_results):
        """TAMPILAN 2: Menggunakan Inisial/Kode Mapel & ID Guru -> Contoh: M08 (G01)"""
        if df_results.empty:
            return pd.DataFrame()
            
        df_results['Display_Code'] = df_results['Kode Mapel'] + " (" + df_results['ID Guru'] + ")"
        matrix = df_results.pivot_table(
            index=['Hari', 'Jam'],
            columns='Kelas',
            values='Display_Code',
            aggfunc='first'
        ).fillna('-')
        return matrix
