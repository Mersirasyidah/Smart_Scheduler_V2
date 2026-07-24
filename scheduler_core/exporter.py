import pandas as pd

class ScheduleExporter:
    @staticmethod
    def format_timetable(df_results):
        """Mengubah format list jadwal menjadi Pivot Table (Matriks Jadwal Kelas)."""
        if df_results is None or df_results.empty:
            return None
            
        pivot_df = df_results.pivot_table(
            index=["Hari", "Jam"],
            columns="Kelas",
            values="Mapel",
            aggfunc=lambda x: " / ".join(x)
        ).fillna("-")
        return pivot_df

    @staticmethod
    def export_to_excel(df_results, file_path="jadwal_terbentuk.xlsx"):
        """Menyimpan jadwal ke format file Excel."""
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df_results.to_excel(writer, sheet_name="Jadwal_Detail", index=False)
            pivot = ScheduleExporter.format_timetable(df_results)
            if pivot is not None:
                pivot.to_excel(writer, sheet_name="Jadwal_Matriks")
        return file_path
