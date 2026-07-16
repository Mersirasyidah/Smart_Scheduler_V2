# scheduler_core/solver.py
import pandas as pd
from ortools.sat.python import cp_model

class SchedulerSolver:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.model = cp_model.CpModel()
        
        # Ambil data dasar
        self.guru = scheduler.guru
        self.rombel = scheduler.rombel
        self.mengajar = scheduler.mengajar
        self.mapel = scheduler.mapel
        self.slot = scheduler.slot  # Hanya slot 'pembelajaran' yang aktif
        
        # List unik kunci
        self.list_guru = self.guru["ID_Guru"].tolist()
        self.list_rombel = self.rombel["ID_Rombel"].tolist()
        self.list_mapel = self.mapel["ID_Mapel"].tolist()
        self.list_hari = self.slot["Hari"].unique().tolist()
        
        # Indexing jam per hari
        self.jam_per_hari = {}
        for hari in self.list_hari:
            self.jam_per_hari[hari] = sorted(self.slot[self.slot["Hari"] == hari]["Jam_Ke"].tolist())
            
        self.variables = {}
        
    def run_solver(self, timeout_seconds=60.0):
        # 1. DEFINISI VARIABEL KEPUTUSAN
        # var[g, r, m, h, j] = 1 jika Guru g, mengajar Rombel r, Mapel m, pada Hari h, Jam j.
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            
            for h in self.list_hari:
                for j in self.jam_per_hari[h]:
                    self.variables[(g, r, m, h, j)] = self.model.NewBoolVar(
                        f"shift_g{g}_r{r}_m{m}_h{h}_j{j}"
                    )
                    
        # 2. BATASAN DASAR (CONSTRAINTS)
        
        # A. Total JP Mingguan Terpenuhi untuk Setiap Tugas Mengajar
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            target_jp = int(row[self.scheduler.col_jp])
            
            self.model.Add(
                sum(self.variables[(g, r, m, h, j)] 
                    for h in self.list_hari 
                    for j in self.jam_per_hari[h]) == target_jp
            )
            
        # B. Satu Kelas Hanya Belajar Satu Mapel pada Satu Jam Tertentu
        for r in self.list_rombel:
            for h in self.list_hari:
                for j in self.jam_per_hari[h]:
                    kelas_active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                        g = row["ID_Guru"]
                        m = row["ID_Mapel"]
                        kelas_active_vars.append(self.variables[(g, r, m, h, j)])
                    
                    self.model.Add(sum(kelas_active_vars) <= 1)
                    
        # C. Satu Guru Hanya Mengajar Satu Kelas pada Satu Jam Tertentu
        for g in self.list_guru:
            for h in self.list_hari:
                for j in self.jam_per_hari[h]:
                    guru_active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Guru"] == g].iterrows():
                        r = row["ID_Rombel"]
                        m = row["ID_Mapel"]
                        guru_active_vars.append(self.variables[(g, r, m, h, j)])
                        
                    self.model.Add(sum(guru_active_vars) <= 1)

        # 3. 🛡️ BATASAN KUALITAS JADWAL (OPTIMASI MUTLAK)

        # ATURAN 1: TIDAK BOLEH LONCAT-LONCAT (NO GAPS IN CLASS SCHEDULE)
        # Menjamin jadwal kelas padat/rapat dari jam mulai hingga jam pulang sekolah di hari itu.
        for r in self.list_rombel:
            for h in self.list_hari:
                jam_list = self.jam_per_hari[h]
                n_jam = len(jam_list)
                if n_jam <= 2:
                    continue
                
                # Variabel pembantu untuk mengetahui apakah kelas "sedang belajar" pada jam j
                is_learning = {}
                for j in jam_list:
                    active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                        active_vars.append(self.variables[(row["ID_Guru"], r, row["ID_Mapel"], h, j)])
                    
                    # is_learning[j] = 1 jika ada pelajaran di kelas r, hari h, jam j
                    is_learning[j] = self.model.NewBoolVar(f"learn_r{r}_h{h}_j{j}")
                    self.model.Add(sum(active_vars) == is_learning[j])

                # Logika Rapat: Jika jam sebelum (j1) dan jam sesudah (j3) ada pelajaran,
                # maka jam di tengahnya (j2) TIDAK BOLEH kosong (wajib ada pelajaran juga).
                for idx in range(n_jam - 2):
                    j1 = jam_list[idx]
                    j2 = jam_list[idx + 1]
                    j3 = jam_list[idx + 2]
                    
                    # Rumus logika: is_learning[j1] + is_learning[j3] - is_learning[j2] <= 1
                    # Jika j1=1 dan j3=1, maka j2 WAJIB bernilai 1 agar pertidaksamaan terpenuhi.
                    self.model.Add(is_learning[j1] + is_learning[j3] - is_learning[j2] <= 1)

        # ATURAN 2: JAM MENGAJAR WAJIB BERURUTAN (CONSECUTIVE BLOCK HOURS)
        # Jika guru mengajar >= 2 JP di kelas & hari yang sama (misal PJOK 3 JP), jamnya harus nempel/berurutan.
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            
            for h in self.list_hari:
                jam_list = self.jam_per_hari[h]
                n_jam = len(jam_list)
                
                # Buat variabel biner penanda apakah guru mengajar di hari tersebut
                is_teaching_today = {}
                for j in jam_list:
                    is_teaching_today[j] = self.variables[(g, r, m, h, j)]
                
                # Jumlah JP yang diajarkan hari ini
                jp_hari_ini = self.model.NewIntVar(0, n_jam, f"jp_count_g{g}_r{r}_m{m}_h{h}")
                self.model.Add(jp_hari_ini == sum(is_teaching_today[j] for j in jam_list))
                
                # Jika JP hari ini >= 2, maka jarak antara jam pertama mengajar dan jam terakhir mengajar
                # harus sama dengan total JP mengajar dikurangi 1 (artinya rapat, tidak boleh ada jeda mapel lain).
                first_jam_idx = self.model.NewIntVar(0, n_jam, f"first_g{g}_r{r}_m{m}_h{h}")
                last_jam_idx = self.model.NewIntVar(0, n_jam, f"last_g{g}_r{r}_m{m}_h{h}")
                
                # Menggunakan trik formulasi rentang indeks jam
                for idx, j in enumerate(jam_list):
                    # Jika mengajar di jam j, maka first_jam_idx <= idx dan last_jam_idx >= idx
                    self.model.Add(first_jam_idx <= idx).OnlyEnforceIf(is_teaching_today[j])
                    self.model.Add(last_jam_idx >= idx).OnlyEnforceIf(is_teaching_today[j])
                    
                # Pembatasan: Rentang mengajar (last - first + 1) harus tepat sama dengan jumlah JP mengajar
                # Hanya diberlakukan jika guru tersebut benar-benar mengajar di hari itu (jp_hari_ini >= 1)
                is_active_today = self.model.NewBoolVar(f"active_today_g{g}_r{r}_m{m}_h{h}")
                self.model.Add(jp_hari_ini >= 1).OnlyEnforceIf(is_active_today)
                self.model.Add(jp_hari_ini == 0).OnlyEnforceIf(is_active_today.Not())
                
                self.model.Add(last_jam_idx - first_jam_idx + 1 == jp_hari_ini).OnlyEnforceIf(is_active_today)

        # ATURAN 3: BATASI MAKSIMAL 3 HINGGA 4 MAPEL SEHARI PER KELAS
        # Membantu siswa fokus dengan mengurangi variasi mata pelajaran harian.
        for r in self.list_rombel:
            for h in self.list_hari:
                mapel_hari_ini_indicators = []
                
                # Cek setiap mapel yang diajarkan di kelas r
                for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                    g = row["ID_Guru"]
                    m = row["ID_Mapel"]
                    
                    # Variabel penanda: 1 jika mapel m diajarkan oleh guru g di kelas r pada hari h
                    has_mapel_today = self.model.NewBoolVar(f"has_m{m}_g{g}_r{r}_h{h}")
                    
                    # Hubungkan penanda dengan jam belajar nyata:
                    # has_mapel_today harus bernilai 1 jika setidaknya ada 1 jam pelajaran aktif
                    self.model.AddMaxEquality(
                        has_mapel_today, 
                        [self.variables[(g, r, m, h, j)] for j in self.jam_per_hari[h]]
                    )
                    mapel_hari_ini_indicators.append(has_mapel_today)
                
                # Total mapel unik dalam sehari untuk kelas ini maksimal 4
                if mapel_hari_ini_indicators:
                    self.model.Add(sum(mapel_hari_ini_indicators) <= 4)

        # 4. SOLVER EXECUTION
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = timeout_seconds
        self.solver.parameters.num_search_workers = 8  # Maksimalkan multi-threading core CPU
        
        status = self.solver.Solve(self.model)
        return status == cp_model.OPTIMAL or status == cp_model.FEASIBLE

    def extract_results(self):
        results = []
        for (g, r, m, h, j), var in self.variables.items():
            if self.solver.Value(var) == 1:
                results.append({
                    "ID_Guru": g,
                    "ID_Rombel": r,
                    "ID_Mapel": m,
                    "Hari": h,
                    "Jam_Ke": j
                })
        return pd.DataFrame(results)
