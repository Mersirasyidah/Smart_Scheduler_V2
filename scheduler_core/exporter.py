import io
import pandas as pd


class ScheduleExporter:

    @staticmethod
    def format_timetable(df_results):
        if df_results is None or df_results.empty:
            return pd.DataFrame()

        # 1. Samakan / Standardisasi nama kolom agar sinkron dengan output solver
        df = df_results.copy()
        column_mapping = {
            "Jam_Ke": "Jam",
            "ID_Rombel": "Rombel",
            "Kelas": "Rombel",
            "ID_Guru": "Guru",
            "ID_Mapel": "Mapel",
        }
        df = df.rename(columns=column_mapping)

        # 2. Cek apakah kolom wajib 'Hari' dan 'Jam' ada
        if "Hari" not in df.columns or "Jam" not in df.columns:
            raise KeyError(
                f"Kolom wajib ('Hari', 'Jam') tidak ditemukan. Kolom yang ada: {list(df.columns)}"
            )

        # 3. Buat teks gabungan untuk isi sel pivot (misal: "IPA (G01)")
        if "Mapel" in df.columns and "Guru" in df.columns:
            df["Info"] = (
                df["Mapel"].astype(str) + " (" + df["Guru"].astype(str) + ")"
            )
        else:
            df["Info"] = df.get("Guru", df.get("Mapel", "KBM"))

        col_target = "Rombel" if "Rombel" in df.columns else df.columns[0]

        # 4. Lakukan Pivot Table
        pivot_df = df.pivot_table(
            index=["Hari", "Jam"],
            columns=col_target,
            values="Info",
            aggfunc=lambda x: " / ".join(str(v) for v in x),
        ).fillna("-")

        return pivot_df

    @staticmethod
    def export_to_excel(df_results):
        # Mencegah error jika df_results kosong/gagal
        if df_results is None or df_results.empty:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                pd.DataFrame({"Status": ["Tidak ada data jadwal"]}).to_excel(
                    writer, index=False
                )
            return buffer.getvalue()

        # Buat pivot
        pivot_df = ScheduleExporter.format_timetable(df_results)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            # Sheet 1: Pivot Matrix
            pivot_df.to_excel(writer, sheet_name="Matriks_Jadwal")
            # Sheet 2: Raw Data
            df_results.to_excel(writer, sheet_name="Data_Mentah", index=False)

        return buffer.getvalue()
