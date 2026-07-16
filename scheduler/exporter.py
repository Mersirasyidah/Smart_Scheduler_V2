# scheduler/exporter.py
import io
import pandas as pd

class ScheduleExporter:
    def __init__(self, df_hasil, db):
        self.df_hasil = df_hasil
        self.db = db
        
    def generate_excel(self):
        """Membuat file Excel dalam bentuk bytes stream agar bisa langsung diunduh lewat Streamlit"""
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Master Jadwal Linier
            self.df_hasil.to_excel(writer, sheet_name="Master_Jadwal", index=False)
            
            # Sheet 2: Format Grid per Rombel/Kelas
            df_grid = self._make_grid_view()
            if not df_grid.empty:
                df_grid.to_excel(writer, sheet_name="Format_Grid_Kelas")
            
        return output.getvalue()

    def _make_grid_view(self):
        """Memformat jadwal linier menjadi bentuk tabel grid silang (Hari/Jam vs Kelas)"""
        if self.df_hasil.empty:
            return pd.DataFrame()
            
        df_temp = self.df_hasil.copy()
        df_temp["Waktu"] = df_temp["Hari"] + " - Jam " + df_temp["Jam"].astype(int).astype(str)
        df_temp["Detail"] = df_temp["Nama Guru"] + "\n(" + df_temp["Mata Pelajaran"] + ")"
        
        try:
            grid = df_temp.pivot(index="Waktu", columns="Kelas", values="Detail")
            return grid.fillna("-")
        except:
            return df_temp
