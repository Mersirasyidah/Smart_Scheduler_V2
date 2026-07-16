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
        self.slot = scheduler.slot
        
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
        self.is_active_day = {} # Variabel penanda keaktifan mengajar per hari
        self.penalties = []
        
    def run_solver(self, timeout_seconds=60.0):
        # 1. DEFINISI VARIABEL KEPUTUSAN UTAMA & PEMBANTU
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            
            for h in self.list_hari:
                # Variabel keputusan utama: Guru g, Rombel r, Mapel m, di Hari h, Jam j
                for j in self.jam_per_hari[h]:
                    self.variables[(g, r, m, h, j)] = self.model.NewBoolVar(
                        f"shift_g{g}_r{r}_m{m}_h{h}_j{j}"
                    )
                
                # Variabel biner pembantu: Apakah ada aktivitas mengajar (g,r,m) pada hari h?
                self.is_active_day[(g, r, m, h)] = self.model.NewBoolVar(f"active_day_g{g}_r{r}_m{m}_h{h}")
                
                # Hubungkan is_active_day dengan variabel jam mengajar harian
                # is_active_day = 1 JIKA DAN HANYA JIKA setidaknya ada 1 jam pelajaran aktif di hari tersebut
                self.model.AddMaxEquality(
                    self.is_active_day[(g, r, m, h)], 
                    [self.variables[(g, r, m, h, j)] for j in self.jam_per_hari[h]]
                )
                    
        # 2. BATASAN MUTLAK (HARD CONSTRAINTS) - WAJIB TERPENUHI
        
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

        # ==========================================
        # 3. 🎯 ATURAN BARU: DISTRIBUSI JP HARIAN & JUMLAH HARI (DIKUNCI MUTLAK)
        # ==========================================
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            target_jp = int(row[self.scheduler.col_jp])
            
            # Kunci 1: Atur Jumlah Hari Mengajar
            # total_hari = jumlah hari aktif mengajar mapel tersebut dalam seminggu
            total_hari = sum(self.is_active_day[(g, r, m, h)] for h in self.list_hari)
            
            # Kunci 2: Atur Porsi JP Mengajar per Hari
            for h in self.list_hari:
                jp_hari_ini = sum(self.variables[(g, r, m, h, j)] for j in self.jam_per_hari[h])
                
                # Aturan Mapel 6 JP -> Harus 3 hari (2 JP, 2 JP, 2 JP)
                if target_jp == 6:
                    self.model.Add(total_hari == 3)
                    # Di hari yang aktif mengajar, porsi JP-nya wajib tepat 2 JP. Jika libur, wajib 0 JP.
                    self.model.Add(jp_hari_ini == 2).OnlyEnforceIf(self.is_active_day[(g, r, m, h)])
                    self.model.Add(jp_hari_ini == 0).OnlyEnforceIf(self.is_active_day[(g, r, m, h)].Not())
                
                # Aturan Mapel 5 JP -> Harus 3 hari (2 JP, 2 JP, 1 JP)
                elif target_jp == 5:
                    self.model.Add(total_hari == 3)
                    # Porsi harian hanya boleh bernilai 1 atau 2 JP (tidak boleh langsung 3 atau 4 JP sekaligus)
                    self.model.Add(jp_hari_ini <= 2).OnlyEnforceIf(self.is_active_day[(g, r, m, h)])
                    self.model.Add(jp_hari_ini >= 1).OnlyEnforceIf(self.is_active_day[(g, r, m, h)])
                    self.model.Add(jp_hari_ini == 0).OnlyEnforceIf(self.is_active_day[(g, r, m, h)].Not())
                
                # Aturan Mapel 3 JP -> Harus langsung 1 hari penuh (langsung 3 JP sekaligus)
                elif target_jp == 3:
                    self.model.Add(total_hari == 1)
                    self.model.Add(jp_hari_ini == 3).OnlyEnforceIf(self.is_active_day[(g, r, m, h)])
                    self.model.Add(jp_hari_ini == 0).OnlyEnforceIf(self.is_active_day[(g, r, m, h)].Not())
                
                # Aturan Mapel 4 JP -> Kita bagi menjadi 2 hari x 2 JP
                elif target_jp == 4:
                    self.model.Add(total_hari == 2)
                    self.model.Add(jp_hari_ini == 2).OnlyEnforceIf(self.is_active_day[(g, r, m, h)])
                    self.model.Add(jp_hari_ini == 0).OnlyEnforceIf(self.is_active_day[(g, r, m, h)].Not())
                
                # Aturan Mapel 2 JP -> Harus 1 hari x 2 JP
                elif target_jp == 2:
                    self.model.Add(total_hari == 1)
                    self.model.Add(jp_hari_ini == 2).OnlyEnforceIf(self.is_active_day[(g, r, m, h)])
                    self.model.Add(jp_hari_ini == 0).OnlyEnforceIf(self.is_active_day[(g, r, m, h)].Not())

        # ==========================================
        # 4. 🛡️ ATURAN STRUKTUR JAM BERURUTAN & TIDAK LONCAT-LONCAT (HARD CONSTRAINTS)
        # ==========================================
        
        # A. Wajib Berurutan (Consecutive Block Hours)
        # Jika suatu mapel terjadwal >= 2 JP pada suatu hari, jam-jam tersebut WAJIB nempel berurutan tanpa jeda mapel lain.
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            
            for h in self.list_hari:
                jam_list = self.jam_per_hari[h]
                n_jam = len(jam_list)
                if n_jam <= 2:
                    continue
                
                is_teaching_today = [self.variables[(g, r, m, h, j)] for j in jam_list]
                
                # Formula biner matematika untuk mencegah "gap" internal mapel di hari yang sama:
                # Jika mengajar di jam idx1 dan idx2, maka tidak boleh ada jeda kosong di antara jam tersebut.
                for idx1 in range(n_jam):
                    for idx2 in range(idx1 + 2, n_jam):
                        for mid_idx in range(idx1 + 1, idx2):
                            # Jika idx1=1 (aktif) dan idx2=1 (aktif), maka mid_idx WAJIB 1 (aktif).
                            self.model.Add(is_teaching_today[idx1] + is_teaching_today[idx2] - is_teaching_today[mid_idx] <= 1)

        # B. Tidak Ada Jam Kosong Di Tengah Jadwal Rombel (No Gaps/Tidak Loncat-Loncat)
        for r in self.list_rombel:
            for h in self.list_hari:
                jam_list = self.jam_per_hari[h]
                n_jam = len(jam_list)
                if n_jam <= 2:
                    continue
                
                is_learning = {}
                for j in jam_list:
                    active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                        active_vars.append(self.variables[(row["ID_Guru"], r, row["ID_Mapel"], h, j)])
                    is_learning[j] = self.model.NewBoolVar(f"learn_r{r}_h{h}_j{j}")
                    self.model.Add(sum(active_vars) == is_learning[j])

                # Mencegah adanya jam kosong di sela-sela waktu belajar aktif rombel
                for idx in range(n_jam - 2):
                    j1 = jam_list[idx]
                    j2 = jam_list[idx + 1]
                    j3 = jam_list[idx + 2]
                    # Jika jam j1 belajar dan jam j3 belajar, maka jam j2 tidak boleh kosong!
                    self.model.Add(is_learning[j1] + is_learning[j3] - is_learning[j2] <= 1)

        # ==========================================
        # 5. 📉 SOFT CONSTRAINTS (PENALTI KUALITAS TAMBAHAN)
        # ==========================================
        
        # Batasi Maksimal 4 Mapel Sehari per Kelas (Penalti jika melanggar)
        for r in self.list_rombel:
            for h in self.list_hari:
                mapel_hari_ini_indicators = []
                for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                    mapel_hari_ini_indicators.append(self.is_active_day[(row["ID_Guru"], r, row["ID_Mapel"], h)])
                
                if mapel_hari_ini_indicators:
                    total_mapel_today = self.model.NewIntVar(0, len(mapel_hari_ini_indicators), f"total_m_r{r}_h{h}")
                    self.model.Add(total_mapel_today == sum(mapel_hari_ini_indicators))
                    
                    over_limit = self.model.NewIntVar(0, len(mapel_hari_ini_indicators), f"over_m_r{r}_h{h}")
                    self.model.Add(over_limit >= total_mapel_today - 4)
                    self.model.Add(over_limit >= 0)
                    self.penalties.append(over_limit * 500)

        # Hubungkan ke fungsi tujuan minimalisasi penalti
        self.model.Minimize(sum(self.penalties))

        # 6. SOLVER EXECUTION
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = timeout_seconds
        self.solver.parameters.num_search_workers = 8  # Optimalisasi Multi-core CPU
        
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
