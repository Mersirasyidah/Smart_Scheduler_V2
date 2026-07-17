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
        # 5. ATURAN PENEMPATAN KETAT (PJOK & MAPEL SULIT/PRIORITAS)
        # =========================================================================
        
        # --- 🚫 A. ATURAN MUTLAK PJOK (MAKSIMAL JAM KE-6, TIDAK BOLEH LEBIH) ---
        MAPEL_PJOK = ["PJOK", "Penyas"]
        
        # Definisi Kelompok Pagi (10 kelas) vs Siang (5 kelas)
        is_kelompok_pagi = {}
        for r in self.list_rombel:
            is_kelompok_pagi[r] = self.model.NewBoolVar(f"pjok_pagi_r{r}")
            
        # Total kelompok pagi harus tepat 10 rombel
        self.model.Add(sum(is_kelompok_pagi[r] for r in self.list_rombel) == 10)
        
        for (g, r, m, h, j), var in self.variables.items():
            if m in MAPEL_PJOK:
                # Batasan Mutlak Global: PJOK sama sekali TIDAK BOLEH di atas jam ke-6!
                if j > 6:
                    self.model.Add(var == 0)
                    
                # Aturan Pembagian Waktu Senin vs Selasa-Jumat
                if h in ["Senin", "SENIN", "senin"]:
                    # Senin Kelompok Pagi: Wajib jam 2-4 (Dilarang jam 1, dilarang jam >= 5)
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r]).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j == 1 or j >= 5))
                    # Senin Kelompok Siang: Wajib jam 4-6 (Dilarang jam <= 3)
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r].Not()).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j <= 3))
                else:
                    # Selasa-Jumat Kelompok Pagi: Wajib jam 1-3 (Dilarang jam >= 4)
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r]).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j >= 4))
                    # Selasa-Jumat Kelompok Siang: Wajib jam 4-6 (Dilarang jam <= 3)
                    self.model.Add(var == 0).OnlyEnforceIf(is_kelompok_pagi[r].Not()).OnlyEnforceIf(self.model.NewBoolVar("").WithEquivalent(j <= 3))

        # --- 🚫 B. BATASAN MUTLAK MAPEL SULIT/PRIORITAS 1 DI JAM PAGI ---
        mapel_prioritas_1 = set()
        if "Prioritas" in self.mapel.columns:
            # Membersihkan spasi dan mencocokkan string/angka '1' secara aman
            prioritas_1_rows = self.mapel[self.mapel["Prioritas"].astype(str).str.strip().str.contains("1")]
            mapel_prioritas_1 = set(prioritas_1_rows["ID_Mapel"].tolist())
        
        # Fallback manual jika kolom di Excel Anda kosong atau tidak terbaca:
        if not mapel_prioritas_1:
            MAPEL_SULIT_FALLBACK = [
                "MAT", "Matematika", "MTK", 
                "IPA", "Fisika", "Biologi", "Kimia",
                "IND", "B_IND", "B_Indo", "Bahasa Indonesia", "B_Indonesia",
                "ING", "B_ING", "B_Ingg", "Bahasa Inggris", "B_Inggris"
            ]
            mapel_prioritas_1 = set(self.mapel[self.mapel["ID_Mapel"].str.upper().isin([x.upper() for x in MAPEL_SULIT_FALLBACK])]["ID_Mapel"].tolist())

        # MENERAPKAN ATURAN KERAS (HARD CONSTRAINT):
        # Mapel Prioritas 1 HANYA BOLEH ditempatkan di Jam 1 s/d Jam 4 (Sesi Pagi).
        # Sama sekali dilarang ditaruh di Jam 5 ke atas!
        for (g, r, m, h, j), var in self.variables.items():
            if m in mapel_prioritas_1:
                # Jika jam mengajar adalah jam ke-5 atau lebih siang, paksa variabel bernilai 0 (tidak boleh aktif)
                if j >= 5:
                    self.model.Add(var == 0)

        # --- 🎯 C. PENALTI: Mapel Ringan/Muatan Lokal di Jam Pagi ---
        # Mapel santai didorong kuat agar tidak mengganggu jam pagi (diberikan penalti jika ditaruh di jam 1-3)
        MAPEL_PRIORITAS_SIANG = ["Prakarya", "PRK", "Bahasa Jawa", "B_Jawa", "BJAW", "SBK", "Seni Budaya"]
        for (g, r, m, h, j), var in self.variables.items():
            if m in MAPEL_PRIORITAS_SIANG and j <= 3:
                self.penalties.append(var * 15000) 

        # --- 🎯 D. INSENTIF: Menempelkan Mapel Ringan di Jam Paling Akhir ---
        for h in self.list_hari:
            if self.jam_per_hari[h]:
                jam_terakhir_list = sorted(self.jam_per_hari[h])[-2:] # Ambil 2 jam terakhir di hari tersebut
                for (g, r, m, h_var, j_var), var in self.variables.items():
                    if m in MAPEL_PRIORITAS_SIANG and h_var == h and j_var not in jam_terakhir_list:
                        self.penalties.append(var * 1500)

        # --- 🎯 E. PENALTI: Batasi Maksimal 4 Mapel Sehari per Kelas ---
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

    # =========================================================================
    # 🎯 KODE DETEKTOR BENTROK OTOMATIS (METODE INTERNAL BARU)
    # =========================================================================
    def periksa_bentrok_jadwal(self, df_hasil):
        """
        Fungsi untuk memeriksa apakah ada guru bentrok, kelas bentrok,
        atau pelanggaran aturan jam mengajar PJOK pada DataFrame hasil.
        """
        print("\n" + "="*50)
        print("🔍 MEMULAI SISTEM VALIDASI & DETEKSI BENTROK JADWAL")
        print("="*50)
        
        ada_bentrok = False
        
        # 1. Cek Bentrok Guru: Satu guru mengajar di > 1 kelas pada jam yang sama
        bentrok_guru = df_hasil[df_hasil.duplicated(subset=['ID_Guru', 'Hari', 'Jam_Ke'], keep=False)]
        if not bentrok_guru.empty:
            print("❌ DETEKSI BENTROK GURU:")
            for _, row in bentrok_guru.sort_values(by=['ID_Guru', 'Hari', 'Jam_Ke']).iterrows():
                print(f"   [BENTROK] Guru {row['ID_Guru']} terdaftar mengajar di Kelas {row['ID_Rombel']} pada hari {row['Hari']} Jam ke-{row['Jam_Ke']}")
            ada_bentrok = True
        else:
            print("✅ Validasi Guru: Aman! Tidak ada guru mengajar di dua kelas berbeda pada jam yang sama.")

        # 2. Cek Bentrok Kelas: Satu kelas menerima > 1 mapel pada jam yang sama
        bentrok_kelas = df_hasil[df_hasil.duplicated(subset=['ID_Rombel', 'Hari', 'Jam_Ke'], keep=False)]
        if not bentrok_kelas.empty:
            print("\n❌ DETEKSI BENTROK KELAS:")
            for _, row in bentrok_kelas.sort_values(by=['ID_Rombel', 'Hari', 'Jam_Ke']).iterrows():
                print(f"   [BENTROK] Kelas {row['ID_Rombel']} menerima pelajaran {row['ID_Mapel']} pada hari {row['Hari']} Jam ke-{row['Jam_Ke']}")
            ada_bentrok = True
        else:
            print("✅ Validasi Kelas: Aman! Tidak ada kelas yang menerima lebih dari satu mata pelajaran di jam yang sama.")
            
        # 3. Cek Aturan PJOK (Tidak boleh > Jam 6)
        MAPEL_PJOK = ["PJOK", "Penyas"]
        pelanggaran_pjok = df_hasil[(df_hasil['ID_Mapel'].isin(MAPEL_PJOK)) & (df_hasil['Jam_Ke'] > 6)]
        if not pelanggaran_pjok.empty:
            print("\n⚠️ PELANGGARAN ATURAN PJOK (> JAM 6):")
            for _, row in pelanggaran_pjok.iterrows():
                print(f"   [MELANGGAR] PJOK Kelas {row['ID_Rombel']} terjadwal di hari {row['Hari']} Jam ke-{row['Jam_Ke']}")
            ada_bentrok = True
        else:
            print("✅ Validasi PJOK: Aman! Semua mapel PJOK sukses ditaruh di bawah jam ke-6.")

        print("="*50)
        if not ada_bentrok:
            print("🎉 JADWAL AMAN TERKENDALI! Silakan ekspor hasilnya.")
        else:
            print("⚠️ PERHATIAN: Masih ada aturan yang dilanggar, silakan sesuaikan jadwal kembali.")
        print("="*50 + "\n")
        
        return not ada_bentrok
