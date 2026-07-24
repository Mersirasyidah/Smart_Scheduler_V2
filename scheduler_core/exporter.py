import pandas as pd


class ScheduleExporter:

  # Daftar Rombel Lengkap 7A - 9E secara terurut
  ALL_ROMBEL = [
      "7A",
      "7B",
      "7C",
      "7D",
      "7E",
      "8A",
      "8B",
      "8C",
      "8D",
      "8E",
      "9A",
      "9B",
      "9C",
      "9D",
      "9E",
  ]

  @staticmethod
  def format_timetable(
      df_results, mapel_df=None, list_rombel=None, slot_df=None
  ):
    """Mengubah dataframe hasil solver menjadi Pivot Table / Matriks Jadwal

    Lengkap untuk semua Rombel (7A - 9E) dan seluruh Jam Pelajaran.
    """
    if df_results is None or df_results.empty:
      return pd.DataFrame()

    df = df_results.copy()

    # 1. Tentukan list rombel target
    target_rombel = list_rombel if list_rombel else ScheduleExporter.ALL_ROMBEL

    # 2. Gabungkan ID_Mapel dengan Nama_Mapel jika dataframe mapel diberikan
    if mapel_df is not None and "ID_Mapel" in df.columns:
      mapel_map = dict(
          zip(
              mapel_df["ID_Mapel"].astype(str).str.strip(),
              mapel_df["Nama_Mapel"].astype(str).str.strip(),
          )
      )
      df["Display_Mapel"] = df["ID_Mapel"].map(mapel_map).fillna(df["ID_Mapel"])
    else:
      df["Display_Mapel"] = df.get("ID_Mapel", df.get("Mapel", ""))

    # Normalize Nama Kolom
    col_hari = "Hari" if "Hari" in df.columns else "Hari"
    col_jam = "Jam_Ke" if "Jam_Ke" in df.columns else "Jam"
    col_rombel = "ID_Rombel" if "ID_Rombel" in df.columns else "Kelas"

    # 3. Buat Pivot Table
    pivot_df = df.pivot_table(
        index=[col_hari, col_jam],
        columns=col_rombel,
        values="Display_Mapel",
        aggfunc=lambda x: " / ".join(x),
    )

    # 4. Pastikan SELURUH Rombel (7A - 9E) muncul sebagai kolom
    pivot_df = pivot_df.reindex(columns=target_rombel, fill_value="-")

    # 5. Urutkan hari sesuai standar pekan
    urutan_hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]
    if col_hari in pivot_df.index.names:
      current_levels = pivot_df.index.levels[0]
      sorted_days = [h for h in urutan_hari if h in current_levels]
      pivot_df = pivot_df.reindex(index=sorted_days, level=0)

    return pivot_df.fillna("-")

  @staticmethod
  def export_to_excel(
      df_results,
      mapel_df=None,
      file_path="jadwal_terbentuk.xlsx",
      list_rombel=None,
  ):
    """Menyimpan jadwal ke file Excel dengan multi-sheet:

    1. Jadwal_Matriks_Kelas (7A-9E) 2. Detail_Jadwal
    """
    target_rombel = list_rombel if list_rombel else ScheduleExporter.ALL_ROMBEL
    pivot_matrix = ScheduleExporter.format_timetable(
        df_results, mapel_df=mapel_df, list_rombel=target_rombel
    )

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
      # Sheet 1: Matriks Jadwal Rombel Lengkap
      if not pivot_matrix.empty:
        pivot_matrix.to_excel(writer, sheet_name="Jadwal_Kelas_7A_9E")

      # Sheet 2: Raw Detail Schedule
      df_results.to_excel(writer, sheet_name="Detail_Jadwal", index=False)

    return file_path
