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
                # Variabel utama: Guru g, Rombel r, Mapel m, di Hari h, Jam j
                for j in self.jam_per_hari[h]:
                    self.variables[(g, r, m, h, j)] = self.model.NewBoolVar(
                        f"shift_g{g}_r{r}_m{m}_h{h}_j{j}"
                    )
                
                # Variabel pembantu: Apakah mengajar (g,r,m) aktif pada hari h?
                self.is_active_day[(g, r, m, h)] = self.model.NewBoolVar(f"active_day_g{g}_r{r}_m{m}_h{h}")
                
                # Hubungkan keaktifan hari dengan jam mengajar
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
            
        # B. Satu Kelas Hanya Belajar Satu Mapel pada Satu Jam
        for r in self.list_rombel:
            for h in self.list_hari:
                for j in self.jam_per_hari[h]:
                    kelas_active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Rombel"] == r].iterrows():
                        g = row["ID_Guru"]
                        m = row["ID_Mapel"]
                        kelas_active_vars.append(self.variables[(g, r, m, h, j)])
                    self.model.Add(sum(kelas_active_vars) <= 1)
                    
        # C. Satu Guru Hanya Mengajar Satu Kelas pada Satu Jam
        for g in self.list_guru:
            for h in self.list_hari:
                for j in self.jam_per_hari[h]:
                    guru_active_vars = []
                    for _, row in self.mengajar[self.mengajar["ID_Guru"] == g].iterrows():
                        r = row["ID_Rombel"]
                        m = row["ID_Mapel"]
                        guru_active_vars.append(self.variables[(g, r, m, h, j)])
                    self.model.Add(sum(guru_active_vars) <= 1)

        # =========================================================================
        # 3. ATURAN PEMBAGIAN JP HARIAN & HARI AKTIF (SOFT CONSTRAINTS PENALTI TINGGI)
        # =========================================================================
        # Menggunakan variabel penyimpangan (deviation) agar AI tidak mogok/infeasible
        for _, row in self.mengajar.iterrows():
            g = row["ID_Guru"]
            r = row["ID_Rombel"]
            m = row["ID_Mapel"]
            target_jp = int(row[self.scheduler.col_jp])
            
            # Hitung total hari aktif mengajar mapel ini
            total_hari = sum(self.is_active_day[(g, r, m, h)] for h in self.list_hari)
            
            # Buat penalti untuk jumlah hari mengajar yang tidak sesuai target
            target_hari = 3 if target_jp in [5, 6] else (2 if target_jp == 4 else 1)
            
            # Penyimpangan Hari (Hari_Kurang dan Hari_Lebih)
            hari_kurang = self.model.NewIntVar(0, 5, f"hari_kurang_g{g}_r{r}_m{m}")
            hari_lebih = self.model.NewIntVar(0, 5, f"hari_lebih_g{g}_r{r}_m{m}")
            self.model.Add(total_hari + hari_kurang - hari_lebih == target_hari)
            
            # Berikan penalti sangat tinggi (10.000) per hari yang melenceng
            self.penalties.append(hari_kurang * 10000)
            self.penalties.append(hari_lebih * 10000)
            
            # Atur porsi JP per hari
            for h in self.list_hari:
                jp_hari_ini = sum(self.variables[(g, r, m, h, j)] for j in self.jam_per_hari[h])
                is_active = self.is_active_day[(g, r, m, h)]
                
                # --- POLA TARGET 6 JP (Wajib 2, 2, 2) ---
                if target_jp == 6:
                    jp_diff = self.model.NewIntVar(-6, 6, f"jp_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(jp_hari_ini - 2 == jp_diff).OnlyEnforceIf(is_active)
                    
                    abs_diff = self.model.NewIntVar(0, 6, f"abs_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(abs_diff >= jp_diff)
                    self.model.Add(abs_diff >= -jp_diff)
                    self.penalties.append(abs_diff * 5000)
                
                # --- POLA TARGET 5 JP (Wajib 2, 2, 1) ---
                elif target_jp == 5:
                    over_2 = self.model.NewIntVar(0, 5, f"over_2_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(over_2 >= jp_hari_ini - 2)
                    self.model.Add(over_2 >= 0)
                    self.penalties.append(over_2 * 8000)
                
                # --- POLA TARGET 3 JP (Wajib langsung 3 JP) ---
                elif target_jp == 3:
                    jp_diff = self.model.NewIntVar(-3, 3, f"jp_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(jp_hari_ini - 3 == jp_diff).OnlyEnforceIf(is_active)
                    
                    abs_diff = self.model.NewIntVar(0, 3, f"abs_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(abs_diff >= jp_diff)
                    self.model.Add(abs_diff >= -jp_diff)
                    self.penalties.append(abs_diff * 8000)
                
                # --- POLA TARGET 4 JP (Wajib 2, 2) ---
                elif target_jp == 4:
                    jp_diff = self.model.NewIntVar(-4, 4, f"jp_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(jp_hari_ini - 2 == jp_diff).OnlyEnforceIf(is_active)
                    
                    abs_diff = self.model.NewIntVar(0, 4, f"abs_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(abs_diff >= jp_diff)
                    self.model.Add(abs_diff >= -jp_diff)
                    self.penalties.append(abs_diff * 5000)
                
                # --- POLA TARGET 2 JP (Wajib langsung 2 JP) ---
                elif target_jp == 2:
                    jp_diff = self.model.NewIntVar(-2, 2, f"jp_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(jp_hari_ini - 2 == jp_diff).OnlyEnforceIf(is_active)
                    
                    abs_diff = self.model.NewIntVar(0, 2, f"abs_diff_g{g}_r{r}_m{m}_h{h}")
                    self.model.Add(abs_diff >= jp_diff)
                    self.model.Add(abs_diff >= -jp_diff)
                    self.penalties.append(abs_diff * 5000)

        # =========================================================================
        # 4. BATASAN STRUKTUR JAM BERURUTAN & TIDAK LONCAT-LONCAT (HARD CONSTRAINTS)
        # =========================================================================
        
        # A. Wajib Berurutan (Consecutive Block Hours)
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
                
                for idx1 in range(n_jam):
                    for idx2 in range(idx1 + 2, n_jam):
                        for mid_idx in range(idx1 + 1, idx2):
                            self.model.Add(is_teaching_today[idx1] + is_teaching_today[idx2] - is_teaching_today[mid_idx] <= 1)

        # B. Tidak Ada Jam Kosong Di Tengah Jadwal Rombel (No Gaps)
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

                for idx in range(n_jam - 2):
                    j1 = jam_list[idx]
                    j2 = jam_list[idx + 1]
                    j3 = jam_list[idx + 2]
                    self.model.Add(is_learning[j1] + is_learning[j3] - is_learning[j2] <= 1)

        # =========================================================================
        # 5. SOFT CONSTRAINTS (PENALTI KUALITAS) & HARD TIME CONSTRAINTS
        # =========================================================================
        
        # --- 🚫 [UPDATE UTAMA] BATASAN MUTLAK PJOK (10 KELAS PAGI, 5 KELAS SIANG) ---
        MAPEL_PJOK = ["PJOK", "Penyas"]
        
        # Buat variabel keputusan keputusan biner untuk masing-masing Rombel (Kelas)
        # 1 = Kelas masuk Kelompok Pagi (Jam 1-3), 0 = Kelas masuk Kelompok Siang (Jam 4-6)
        is_kelompok_pagi = {}
        for r in self.list_rombel:
            is_kelompok_pagi[r] = self.model.NewBoolVar(f"pjok_pagi_r{r}")
            
        # Aturan Keras: Total kelas di kelompok pagi HARUS tepat 10 kelas
        self.model.Add(sum(is_kelompok_pagi[r] for r in self.list_rombel) == 10)
        
        for (g, r, m, h, j), var in self.variables.items():
            if m in MAPEL_PJOK:
                # --- ATURAN HARI SENIN (Khusus) ---
                if h in ["Senin", "SENIN", "senin"]:
                    # Senin Pagi (Kelompok Pagi): Wajib Jam 2, 3, 4 (karena Jam 1 dipakai upacara)
                    # Jika kelas masuk kelompok pagi, dilarang di Jam 1 ATAU Jam >= 5
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r]).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j == 1 or j >= 5))
                    
                    # Senin Siang (Kelompok Siang): Wajib Jam 4, 5, 6
                    # Jika kelas masuk kelompok siang, dilarang di Jam 1-3 ATAU Jam >= 7
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r].Not()).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j <= 3 or j >= 7))
                
                # --- ATURAN SELASA S/D JUMAT ---
                else:
                    # Selasa-Jumat Pagi (Kelompok Pagi): Wajib Jam 1, 2, 3
                    # Dilarang di Jam >= 4 jika terpilih kelompok pagi
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r]).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j >= 4))
                    
                    # Selasa-Jumat Siang (Kelompok Siang): Wajib Jam 4, 5, 6
                    # Dilarang di Jam <= 3 ATAU Jam >= 7 jika kelompok siang
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r].Not()).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j <= 3 or j >= 7))

        # --- 🎯 PENALTI: Matematika Diupayakan di Jam Pagi (Jam 1 - 4) ---
        MAPEL_MATEMATIKA = ["MAT", "Matematika"]
        for (g, r, m, h, j), var in self.variables.items():
            # Jika Matematika ditaruh di jam ke-5 atau lebih siang
            if m in MAPEL_MATEMATIKA and j >= 5:
                self.penalties.append(var * 8000) # Penalti tinggi agar AI menaruhnya di pagi

        # --- 🎯 PENALTI: Mapel Siang/Muatan Lokal (Prakarya & Bahasa Jawa) ---
        MAPEL_PRIORITAS_SIANG = ["Prakarya", "PRK", "Bahasa Jawa", "B_Jawa", "BJAW", "SBK", "Seni Budaya"]
        for (g, r, m, h, j), var in self.variables.items():
            # Jika mapel santai ditaruh di jam pagi (jam ke-1 s/d jam ke-4)
            if m in MAPEL_PRIORITAS_SIANG and j <= 4:
                self.penalties.append(var * 6000) # Beri denda agar digeser ke siang

        # --- 🎯 INSENTIF: Menempelkan Prakarya & B. Jawa di Jam Paling Akhir ---
        for h in self.list_hari:
            if self.jam_per_hari[h]:
                jam_terakhir_list = sorted(self.jam_per_hari[h])[-2:] # Ambil 2 jam terakhir di hari tersebut
                for (g, r, m, h_var, j_var), var in self.variables.items():
                    # Jika ditempatkan di luar 2 jam terakhir hari tersebut, beri penalti ringan
                    if m in MAPEL_PRIORITAS_SIANG and h_var == h and j_var not in jam_terakhir_list:
                        self.penalties.append(var * 1500)

        # --- 🎯 PENALTI: Batasi Maksimal 4 Mapel Sehari per Kelas ---
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
                    self.penalties.append(over_limit * 300)

        # Hubungkan seluruh penalti ke fungsi objektif minimalisasi
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
