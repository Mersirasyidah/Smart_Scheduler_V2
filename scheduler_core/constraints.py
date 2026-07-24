class ConstraintManager:
    def __init__(self, data):
        self.guru_df = data["guru"]
        self.mapel_df = data["mapel"]
        self.mengajar_df = data["guru_mengajar"]
        self.hari_jam_df = data["hari_jam"]

    def get_teacher_mgmp_days(self):
        mgmp_dict = {}
        for _, row in self.guru_df.iterrows():
            if pd.notna(row["Hari MGMP"]):
                mgmp_dict[str(row["ID Guru"]).strip()] = str(row["Hari MGMP"]).strip()
        return mgmp_dict

    def get_lesson_splits(self):
        assignments = []
        for idx, row in self.mengajar_df.iterrows():
            splits_str = str(row["Pembagian"])
            try:
                splits = [int(s.strip()) for s in splits_str.split(",")]
            except ValueError:
                splits = [int(row["JP"])]
            
            assignments.append({
                "id": idx,
                "guru_id": str(row["ID Guru"]).strip(),
                "guru_nama": row["Nama Guru"],
                "mapel": row["Mapel"],
                "kelas": row["Kelas"],
                "total_jp": row["JP"],
                "splits": splits
            })
        return assignments

# Alias agar aman jika dipanggil dengan nama ConstraintBuilder
ConstraintBuilder = ConstraintManager
