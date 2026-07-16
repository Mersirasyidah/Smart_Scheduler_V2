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
        # List untuk menampung pinalti/biaya optimasi
        self.penalties = []
        
    def run_solver(self, timeout_seconds=60.0):
        # 1. DEFINISI VARIABEL KEPUTUSAN
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            
            for h in self.list_hari:
                for j in self.jam_per_hari[h]:
                    self.variables[(g, r, m, h, j)] = self.model.NewBoolVar(
                        f"shift_g{g}_r{r}_m{m}_h{h}_j{j}"
                    )
                    
        # 2. BATASAN MUTLAK (HARD CONSTRAINTS) - Wajib Terpenuhi
        
        # A. Total JP Mingguan Terpenuhi
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

        # 3. 🎯 SOFT CONSTRAINTS & PENALTI (OPTIMASI FLEKSIBEL)
        # Menghindari kegagalan pencarian solusi dengan memberikan penalti jika melanggar kualitas ideal.

        # Kata kunci mapel blok yang diprioritaskan rapat
        kata_kunci_pjok = ["pjok", "olahraga", "jasmani", "penjas", "penjasorkes"]
        kata_kunci_agama = ["agama", "islam", "kristen", "katolik", "hindu", "buddha", "konghucu"]
        
        # SOFT ATURAN 1: PENALTI UNTUK JAM KOSONG DI TENGAH (NO GAPS)
        for r in self.list_rombel:
            for h in self.list_hari:
                jam_list = self.jam_per_hari[h]
                n_jam = len(jam_list)
                if n_jam <= 2:
                    continue
                
                # Buat variabel apakah ada pelajaran di jam j
                is_learning = {}
                for j in jam_list:
                    active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                        active_vars.append(self.variables[(row["ID_Guru"], r, row["ID_Mapel"], h, j)])
                    is_learning[j] = self.model.NewBoolVar(f"learn_r{r}_h{h}_j{j}")
                    self.model.Add(sum(active_vars) == is_learning[j])

                # Jika jam j1 ada, j3 ada, tapi j2 kosong -> berikan penalti tinggi (100)
                for idx in range(n_jam - 2):
                    j1 = jam_list[idx]
                    j2 = jam_list[idx + 1]
                    j3 = jam_list[idx + 2]
                    
                    gap_detected = self.model.NewBoolVar(f"gap_r{r}_h{h}_{j1}_{j2}_{j3}")
                    # gap_detected aktif jika is_learning[j1] + is_learning[j3] - is_learning[j2] == 2 (yaitu j1=1, j3=1, j2=0)
                    self.model.Add(is_learning[j1] + is_learning[j3] - is_learning[j2] <= 1 + gap_detected)
                    
                    # Tambah beban pinalti ke fungsi objektif
                    self.penalties.append(gap_detected * 100)

        # SOFT ATURAN 2: PENALTI UNTUK MAPEL YANG TERPISAH (NOT CONSECUTIVE)
        # Khusus untuk PJOK, Agama, atau mapel >= 2 JP dalam satu hari agar nempel berurutan.
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            mapel_name = str(row["ID_Mapel"]).lower()
            
            # Berikan bobot penalti lebih besar untuk PJOK (500) dan Agama (400) agar diutamakan rapat
            is_pjok = any(k in mapel_name for k in kata_kunci_pjok)
            is_agama = any(k in mapel_name for k in kata_kunci_agama)
            bobot_penalti = 1000 if is_pjok else (800 if is_agama else 150)
            
            for h in self.list_hari:
                jam_list = self.jam_per_hari[h]
                n_jam = len(jam_list)
                if n_jam <= 2:
                    continue
                
                is_teaching_today = [self.variables[(g, r, m, h, j)] for j in jam_list]
                
                # Deteksi jika ada 'lompatan' mengajar mapel yang sama oleh guru yang sama di hari yang sama
                for idx1 in range(n_jam):
                    for idx2 in range(idx1 + 2, n_jam):
                        # Jika mengajar di jam idx1 dan idx2, tetapi di antaranya (idx1 + 1) tidak mengajar
                        # Ini mengindikasikan adanya pemisahan/gap mengajar kelas yang sama
                        for mid_idx in range(idx1 + 1, idx2):
                            split_detected = self.model.NewBoolVar(f"split_g{g}_r{r}_m{m}_h{h}_{idx1}_{mid_idx}_{idx2}")
                            # Aktif jika mengajar di idx1 dan idx2 tapi kosong di mid_idx
                            self.model.Add(is_teaching_today[idx1] + is_teaching_today[idx2] - is_teaching_today[mid_idx] <= 1 + split_detected)
                            self.penalties.append(split_detected * bobot_penalti)

        # SOFT ATURAN 3: MAKSIMAL 4 MAPEL SEHARI
        # Jika satu kelas belajar > 4 mapel dalam sehari, berikan penalti sedang (300) per kelebihan mapel.
        for r in self.list_rombel:
            for h in self.list_hari:
                mapel_hari_ini_indicators = []
                for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                    g = row["ID_Guru"]
                    m = row["ID_Mapel"]
                    
                    has_mapel_today = self.model.NewBoolVar(f"has_m{m}_g{g}_r{r}_h{h}")
                    self.model.AddMaxEquality(has_mapel_today, [self.variables[(g, r, m, h, j)] for j in self.jam_per_hari[h]])
                    mapel_hari_ini_indicators.append(has_mapel_today)
                
                if mapel_hari_ini_indicators:
                    total_mapel_today = self.model.NewIntVar(0, len(mapel_hari_ini_indicators), f"total_m_r{r}_h{h}")
                    self.model.Add(total_mapel_today == sum(mapel_hari_ini_indicators))
                    
                    over_limit = self.model.NewIntVar(0, len(mapel_hari_ini_indicators), f"over_m_r{r}_h{h}")
                    # over_limit = max(0, total_mapel_today - 4)
                    self.model.Add(over_limit >= total_mapel_today - 4)
                    self.model.Add(over_limit >= 0)
                    
                    self.penalties.append(over_limit * 300)

        # SOFT ATURAN 4: PJOK HARUS DI JAM PAGI (JAM 1-3)
        # Berikan penalti jika PJOK diletakkan di luar Jam 1, 2, atau 3.
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            mapel_name = str(row["ID_Mapel"]).lower()
            
            if any(k in mapel_name for k in kata_kunci_pjok):
                for h in self.list_hari:
                    for idx, j in enumerate(self.jam_per_hari[h]):
                        # Jam ke-1, 2, 3 biasanya berada di indeks 0, 1, 2. Jika indeks > 2 (artinya jam siang)
                        if idx > 2:
                            pjok_siang = self.variables[(g, r, m, h, j)]
                            self.penalties.append(pjok_siang * 500) # Berikan pinalti 500 jika olahraga di siang hari

        # 4. FUNGSI MINIMALISASI PENALTI (OBJECTIVE FUNCTION)
        # AI akan meminimalkan total penalti, sehingga menghasilkan jadwal yang mendekati sempurna secara otomatis!
        self.model.Minimize(sum(self.penalties))

        # 5. SOLVER EXECUTION
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
