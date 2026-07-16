# scheduler_core/exporter.py
import io
import pandas as pd

class ScheduleExporter:
    def __init__(self, df_hasil, db):
        self.df_hasil = df_hasil
        self.db = db
        self.guru = db["Guru"]
        self.rombel = db["Rombel"]
        self.mapel = db["Mapel"]

    def generate_excel(self):
        """Membuat file Excel di memori (BytesIO) agar bisa langsung diunduh lewat Streamlit"""
        output = io.BytesIO()
        
        # Gabungkan data ID dengan nama asli agar jadwal mudah dibaca manusia
        df_rich = self.df_hasil.merge(self.guru, on="ID_Guru", how="left")
        df_rich = df_rich.merge(self.rombel, on="ID_Rombel", how="left")
        df_rich = df_rich.merge(self.mapel, on="ID_Mapel", how="left")
        
        # Pilih kolom yang relevan untuk lembar utama
        df_cetak = df_rich[[
            "Hari", "Jam_Ke", "Nama_Rombel", "Nama_Guru", "Nama_Mapel"
        ]].copy()
        df_cetak.columns = ["Hari", "Jam Ke", "Kelas / Rombel", "Nama Guru", "Mata Pelajaran"]

        # Tulis ke file Excel menggunakan openpyxl engine
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Sheet 1: Jadwal Vertikal (Semua Kelas)
            df_cetak.to_excel(writer, sheet_name="Jadwal_Semua_Kelas", index=False)
            
            # Sheet 2: Format Matriks (Jadwal per Rombel agar mudah dibaca per kelas)
            matriks_list = []
            for kelas in df_cetak["Kelas / Rombel"].unique():
                df_kelas = df_cetak[df_cetak["Kelas / Rombel"] == kelas]
                pivot_kelas = df_kelas.pivot(
                    index="Jam Ke", 
                    columns="Hari", 
                    values="Nama Guru"
                )
                # Tambahkan penanda nama kelas di dalam sheet nanti
                matriks_list.append((kelas, pivot_kelas))
            
            # Tulis matriks kelas ke sheet terpisah demi kemudahan pembacaan
            for kelas, pivot_df in matriks_list:
                # Batasi panjang nama sheet maksimal 30 karakter agar tidak error di Excel
                sheet_title = f"Kelas_{str(kelas)[:20]}"
                pivot_df.to_excel(writer, sheet_name=sheet_title)

        # Kembalikan file binary Excel
        return output.getvalue()
