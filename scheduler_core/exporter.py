# scheduler_core/exporter.py
import io
import pandas as pd


class ScheduleExporter:

    def __init__(self, df_hasil, db):
        self.df_hasil = df_hasil.copy()

        # Konversi db ke dict DataFrame jika berupa objek DataLoader/pustaka
        if isinstance(db, dict):
            self.guru = db["Guru"].copy()
            self.rombel = db["Rombel"].copy()
            self.mapel = db["Mapel"].copy()
        else:
            self.guru = db.guru.copy()
            self.rombel = db.rombel.copy()
            self.mapel = db.mapel.copy()

        # Sanitasi nama kolom database
        for df in [self.guru, self.rombel, self.mapel]:
            df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]

    def generate_excel(self):
        """Membuat file Excel di memori (BytesIO) untuk diunduh via Streamlit"""
        output = io.BytesIO()

        if self.df_hasil.empty:
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                pd.DataFrame({"Pesan": ["Data jadwal kosong"]}).to_excel(
                    writer, sheet_name="Jadwal", index=False
                )
            return output.getvalue()

        # 1. Menyesuaikan nama kolom ID Rombel pada sheet Rombel
        rombel_df = self.rombel.copy()
        if "Kelas" in rombel_df.columns and "ID_Rombel" not in rombel_df.columns:
            rombel_df["ID_Rombel"] = rombel_df["Kelas"]

        # 2. Merge data ID dengan detail lengkap dari sheet Guru, Rombel, dan Mapel
        df_rich = self.df_hasil.merge(self.guru, on="ID_Guru", how="left")
        df_rich = df_rich.merge(rombel_df, on="ID_Rombel", how="left")
        df_rich = df_rich.merge(self.mapel, on="ID_Mapel", how="left")

        # Deteksi otomatis nama kolom kelas/rombel
        col_kelas = (
            "Kelas"
            if "Kelas" in df_rich.columns
            else (
                "Nama_Rombel"
                if "Nama_Rombel" in df_rich.columns
                else "ID_Rombel"
            )
        )
        col_guru = (
            "Nama_Guru" if "Nama_Guru" in df_rich.columns else "ID_Guru"
        )
        col_mapel = (
            "Nama_Mapel" if "Nama_Mapel" in df_rich.columns else "ID_Mapel"
        )

        # Buat kolom gabungan untuk isi sel matriks/pivot: "Nama Mapel (Nama Guru)"
        df_rich["Mapel_Guru"] = (
            df_rich[col_mapel].fillna("-").astype(str)
            + "\n("
            + df_rich[col_guru].fillna("-").astype(str)
            + ")"
        )

        # DataFrame cetak utama (Bentuk Tabel Vertikal)
        df_cetak = df_rich[
            ["Hari", "Jam_Ke", col_kelas, col_guru, col_mapel]
        ].copy()
        df_cetak.columns = [
            "Hari",
            "Jam Ke",
            "Kelas / Rombel",
            "Nama Guru",
            "Mata Pelajaran",
        ]

        # Urutkan berdasarkan Hari & Jam
        urutan_hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]
        df_cetak["Hari_Num"] = df_cetak["Hari"].map(
            lambda x: (
                urutan_hari.index(x) if x in urutan_hari else 99
            )
        )
        df_cetak = df_cetak.sort_values(
            by=["Hari_Num", "Kelas / Rombel", "Jam Ke"]
        ).drop(columns=["Hari_Num"])

        # 3. Tulis ke Excel (Menggunakan openpyxl)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Sheet 1: Jadwal Vertikal / Master
            df_cetak.to_excel(
                writer, sheet_name="Jadwal_Semua_Kelas", index=False
            )

            # Sheet 2: Matriks Per Kelas (Pivot)
            for kelas in df_rich[col_kelas].unique():
                df_k = df_rich[df_rich[col_kelas] == kelas]

                pivot_k = df_k.pivot(
                    index="Jam_Ke", columns="Hari", values="Mapel_Guru"
                ).fillna("-")

                # Atur ulang urutan kolom Hari pada Pivot jika ada
                existing_days = [
                    h for h in urutan_hari if h in pivot_k.columns
                ]
                pivot_k = pivot_k[existing_days]

                sheet_title = f"Kelas_{str(kelas)[:20]}"
                pivot_k.to_excel(writer, sheet_name=sheet_title)

        return output.getvalue()
