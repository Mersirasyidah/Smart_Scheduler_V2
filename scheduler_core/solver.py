import os
import pandas as pd
from ortools.sat.python import cp_model

# 1. Path dinamis agar aman di lokal maupun Streamlit Cloud
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
excel_path = os.path.join(BASE_DIR, 'database_scheduler.xlsx')

# Fallback ke folder 'data' jika di root tidak ada
if not os.path.exists(excel_path):
    excel_path = os.path.join(BASE_DIR, 'data', 'database_scheduler.xlsx')

guru_df = pd.read_excel(excel_path, sheet_name='Guru')
mapel_df = pd.read_excel(excel_path, sheet_name='Mapel')
rombel_df = pd.read_excel(excel_path, sheet_name='Rombel')
mengajar_df = pd.read_excel(excel_path, sheet_name='Guru_Mengajar')
slot_df = pd.read_excel(excel_path, sheet_name='Hari_Jam')

# Standardize columns
for df in [guru_df, rombel_df, mengajar_df, mapel_df, slot_df]:
    df.columns = [c.replace(" ", "_") for c in df.columns]

# Perbaikan Bahasa Jawa
mengajar_df.loc[mengajar_df['Mapel'] == 'Bahasa Jawa', 'JP'] = 2
mengajar_df.loc[mengajar_df['Mapel'] == 'Bahasa Jawa', 'Pembagian'] = '2'

print("Total JP per kelas setelah perbaikan Bahasa Jawa = 2:")
print(mengajar_df.groupby('Kelas')['JP'].sum())


class TestScheduler:
    def __init__(self, guru, rombel, mengajar, mapel, slot):
        self.guru = guru
        self.rombel = rombel
        self.mengajar = mengajar
        self.mapel = mapel
        self.slot = slot

        self.list_guru = self.guru["ID_Guru"].tolist()
        self.list_rombel = (
            self.rombel["Kelas"].tolist()
            if "Kelas" in self.rombel.columns
            else self.rombel["ID_Rombel"].tolist()
        )
        self.list_mapel = self.mapel["ID_Mapel"].tolist()
        self.list_hari = self.slot["Hari"].unique().tolist()

        slot_belajar = self.slot[self.slot["Jenis"].str.upper() == "PEMBELAJARAN"]
        self.jam_per_hari = {}
        for hari in self.list_hari:
            self.jam_per_hari[hari] = sorted(
                slot_belajar[slot_belajar["Hari"] == hari]["Jam"]
                .dropna()
                .astype(int)
                .tolist()
            )

        self.tugas_mengajar = []
        tugas_id = 0
        mapel_mapping = dict(
            zip(self.mapel['Nama_Mapel'].str.strip().str.upper(), self.mapel['ID_Mapel'])
        )

        for _, row in self.mengajar.iterrows():
            guru = row["ID_Guru"]
            rombel = row["Kelas"] if "Kelas" in self.mengajar.columns else row["ID_Rombel"]
            mapel_nama = str(row["Mapel"]).strip().upper()
            mapel_id = mapel_mapping.get(mapel_nama, row.get("ID_Mapel", "M99"))

            pembagian_str = str(row["Pembagian"]).strip()
            if "," in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(",") if x.strip().isdigit()]
            elif "." in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(".") if x.strip().isdigit()]
            else:
                try:
                    list_jp = [int(float(pembagian_str))]
                except Exception:
                    list_jp = [int(row["JP"])]

            for jp_blok in list_jp:
                if jp_blok > 0:
                    self.tugas_mengajar.append({
                        "id_tugas": tugas_id,
                        "guru": guru,
                        "rombel": rombel,
                        "mapel": mapel_id,
                        "jp": jp_blok
                    })
                    tugas_id += 1

        self.mapel_pjok = set()
        for _, row in self.mapel.iterrows():
            kode = str(row["ID_Mapel"]).strip().upper()
            if kode == "M11" or "JASMANI" in str(row["Nama_Mapel"]).upper():
                self.mapel_pjok.add(row["ID_Mapel"])


def solve_with_flags(scheduler, lock_agama=True, pjok_max6=True, max4mapel=True):
    model = cp_model.CpModel()
    variables = {}

    for t in scheduler.tugas_mengajar:
        t_id = t["id_tugas"]
        for hari in scheduler.list_hari:
            for jam in scheduler.jam_per_hari[hari]:
                variables[(t_id, hari, jam)] = model.NewBoolVar(f"t_{t_id}_{hari}_{jam}")

    tugas_hari_aktif = {}
    for t in scheduler.tugas_mengajar:
        t_id = t["id_tugas"]
        for hari in scheduler.list_hari:
            tugas_hari_aktif[(t_id, hari)] = model.NewBoolVar(f"aktif_t_{t_id}_{hari}")
            model.AddMaxEquality(
                tugas_hari_aktif[(t_id, hari)],
                [variables[(t_id, hari, jam)] for jam in scheduler.jam_per_hari[hari]]
            )

    for t in scheduler.tugas_mengajar:
        t_id = t["id_tugas"]
        mapel = t["mapel"]
        rombel = t["rombel"]

        # Total jam per tugas harus sama dengan JP
        model.Add(
            sum(
                variables[(t_id, hari, jam)]
                for hari in scheduler.list_hari
                for jam in scheduler.jam_per_hari[hari]
            ) == t["jp"]
        )
        
        # Tugas hanya boleh dilaksanakan di 1 hari saja
        model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in scheduler.list_hari) == 1)

        # Kunci Agama (M01)
        if lock_agama and mapel == "M01" and rombel in ["7A", "8A", "8C", "9A"]:
            # Cari nama hari Kamis yang cocok (case-insensitive)
            kamis_key = next((h for h in scheduler.list_hari if h.strip().lower() == "kamis"), None)
            if kamis_key:
                model.Add(tugas_hari_aktif[(t_id, kamis_key)] == 1)

        # PJOK Maksimal Jam ke-6
        if pjok_max6 and mapel in scheduler.mapel_pjok:
            for hari in scheduler.list_hari:
                for jam in scheduler.jam_per_hari[hari]:
                    if jam > 6:
                        model.Add(variables[(t_id, hari, jam)] == 0)

    # Maksimal Mapel per Hari per Rombel
    if max4mapel:
        for rombel in scheduler.list_rombel:
            for hari in scheduler.list_hari:
                mapel_aktif_hari = []
                for mapel in scheduler.list_mapel:
                    tugas_mapel = [
                        t["id_tugas"]
                        for t in scheduler.tugas_mengajar
                        if t["rombel"] == rombel and t["mapel"] == mapel
                    ]
                    if tugas_mapel:
                        is_active = model.NewBoolVar(f"active_{rombel}_{mapel}_{hari}")
                        model.AddMaxEquality(
                            is_active,
                            [tugas_hari_aktif[(t_id, hari)] for t_id in tugas_mapel]
                        )
                        mapel_aktif_hari.append(is_active)

                if mapel_aktif_hari:
                    # Diregangkan ke <= 5 atau 6 jika <= 4 membuat jadwal infeasible
                    model.Add(sum(mapel_aktif_hari) <= 5)

    # Dilarang lebih dari 1 pertemuan mapel yang sama per hari
    for rombel in scheduler.list_rombel:
        for mapel in scheduler.list_mapel:
            tugas_sama = [
                t["id_tugas"]
                for t in scheduler.tugas_mengajar
                if t["rombel"] == rombel and t["mapel"] == mapel
            ]
            if len(tugas_sama) > 1:
                for hari in scheduler.list_hari:
                    model.Add(sum(tugas_hari_aktif[(t_id, hari)] for t_id in tugas_sama) <= 1)

    # Batasan Konflik Rombel
    for rombel in scheduler.list_rombel:
        tugas_rombel = [t["id_tugas"] for t in scheduler.tugas_mengajar if t["rombel"] == rombel]
        for hari in scheduler.list_hari:
            for jam in scheduler.jam_per_hari[hari]:
                model.Add(sum(variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1)

    # Batasan Konflik Guru
    for guru in scheduler.list_guru:
        tugas_guru = [t["id_tugas"] for t in scheduler.tugas_mengajar if t["guru"] == guru]
        for hari in scheduler.list_hari:
            for jam in scheduler.jam_per_hari[hari]:
                model.Add(sum(variables[(t_id, hari, jam)] for t_id in tugas_guru) <= 1)

    # Perbaikan Sliding Window (Jam Mengajar Berurutan/Blok)
    for t in scheduler.tugas_mengajar:
        t_id = t["id_tugas"]
        target_jp = t["jp"]
        if target_jp > 1:
            for hari in scheduler.list_hari:
                jam_hari = scheduler.jam_per_hari[hari]
                start_vars = []
                num_windows = len(jam_hari) - target_jp + 1
                
                if num_windows > 0:
                    for i in range(num_windows):
                        s_var = model.NewBoolVar(f"start_{t_id}_{hari}_{jam_hari[i]}")
                        start_vars.append(s_var)
                        
                        # Jika window ini aktif, maka jam di dalam window bernilai 1
                        for offset in range(target_jp):
                            model.Add(variables[(t_id, hari, jam_hari[i + offset])] == 1).OnlyEnforceIf(s_var)
                            
                    # Tepat 1 window yang aktif jika tugas aktif di hari tersebut
                    model.Add(sum(start_vars) == tugas_hari_aktif[(t_id, hari)])
                else:
                    # Jika jumlah jam di hari tersebut kurang dari blok JP tugas
                    model.Add(tugas_hari_aktif[(t_id, hari)] == 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15
    solver.parameters.num_search_workers = 4
    
    status_code = solver.Solve(model)
    status_name = solver.StatusName(status_code)
    return status_name


ts = TestScheduler(guru_df, rombel_df, mengajar_df, mapel_df, slot_df)

print("1. Default All Constraints:", solve_with_flags(ts, True, True, True))
print("2. Lock Agama OFF:", solve_with_flags(ts, False, True, True))
print("3. Max Mapel OFF:", solve_with_flags(ts, True, True, False))
