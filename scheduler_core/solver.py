import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:

    def __init__(self, scheduler):

        self.scheduler = scheduler
        self.model = cp_model.CpModel()

        # =====================================================
        # DATA MASTER (Menyesuaikan penamaan kolom Excel Anda)
        # =====================================================
        self.guru = scheduler.guru.copy()
        self.rombel = scheduler.rombel.copy()
        self.mengajar = scheduler.mengajar.copy()
        self.mapel = scheduler.mapel.copy()
        self.slot = scheduler.slot.copy()

        # Standardisasi nama kolom agar aman dari variasi spasi/underscore
        for df in [self.guru, self.rombel, self.mengajar, self.mapel, self.slot]:
            df.columns = [c.replace(" ", "_") for c in df.columns]

        # Master list data
        self.list_guru = self.guru["ID_Guru"].tolist()
        self.list_rombel = self.rombel["Kelas"].tolist() if "Kelas" in self.rombel.columns else self.rombel["ID_Rombel"].tolist()
        self.list_mapel = self.mapel["ID_Mapel"].tolist()
        self.list_hari = self.slot["Hari"].unique().tolist()

        # Jam per hari
        self.jam_per_hari = {}
        # Filter hanya untuk baris Jenis 'Pembelajaran' agar jam Upacara/Istirahat tidak diisi
        slot_belajar = self.slot[self.slot["Jenis"].str.upper() == "PEMBELAJARAN"]
        for hari in self.list_hari:
            self.jam_per_hari[hari] = sorted(
                slot_belajar[slot_belajar["Hari"] == hari]["Jam"].dropna().astype(int).tolist()
            )

        # =====================================================
        # PARSING PEMBAGIAN JP (Kunci agar tidak Infeasible)
        # =====================================================
        self.tugas_mengajar = []
        tugas_id = 0
        
        for _, row in self.mengajar.iterrows():
            guru = row["ID_Guru"]
            # Mendukung nama kolom 'Kelas' atau 'ID_Rombel'
            rombel = row["Kelas"] if "Kelas" in self.mengajar.columns else row["ID_Rombel"]
            
            # Cari ID Mapel berdasarkan nama mapel dari tabel Master Mapel
            mapel_nama = row["Mapel"]
            match_mapel = self.mapel[self.mapel["Nama_Mapel"].str.upper() == str(mapel_nama).strip().upper()]
            if not match_mapel.empty:
                mapel_id = match_mapel.iloc[0]["ID_Mapel"]
            else:
                mapel_id = row.get("ID_Mapel", "M99")

            pembagian_str = str(row["Pembagian"]).strip()
            
            # Deteksi pecahan blok jam (Contoh: "2,2,1" atau "2.2" atau "3")
            if "," in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(",") if x.strip().isdigit()]
            elif "." in pembagian_str:
                list_jp = [int(x) for x in pembagian_str.split(".") if x.strip().isdigit()]
            else:
                try:
                    list_jp = [int(float(pembagian_str))]
                except:
                    list_jp = [int(row["JP"])]

            # Pecah menjadi sub-tugas independen per hari
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

        # =====================================================
        # KATEGORI MAPEL (Otomatis deteksi Shift dari Excel)
        # =====================================================
        self.mapel_prioritas_pagi = set()
        self.mapel_pjok = set()
        self.mapel_prioritas_siang = set()
        self.mapel_normal = set()

        for _, row in self.mapel.iterrows():
            kode = str(row["ID_Mapel"]).strip().upper()
            shift = str(row.get("Shift", "")).strip().upper()
            
            if kode == "M11" or "JASMANI" in str(row["Nama_Mapel"]).upper():
                self.mapel_pjok.add(row["ID_Mapel"])
            elif shift == "PAGI" or row.get("Prioritas", 3) == 1:
                self.mapel_prioritas_pagi.add(row["ID_Mapel"])
            elif shift == "SIANG":
                self.mapel_prioritas_siang.add(row["ID_Mapel"])
            else:
                self.mapel_normal.add(row["ID_Mapel"])

        self.variables = {}

    # =====================================================
    # RUN SOLVER
    # =====================================================
    def run_solver(self, timeout_seconds=120):
        print(f"Total Sub-Tugas hasil ekstraksi blok: {len(self.tugas_mengajar)}")

        # 1. Membuat Variabel Keputusan Berbasis Blok Tugas
        # x[tugas, hari, jam] = 1 jika sub-tugas aktif di slot tersebut
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.variables[(t_id, hari, jam)] = self.model.NewBoolVar(f"t_{t_id}_{hari}_{jam}")

        # 2. Variabel Pembantu: Apakah sub-tugas diambil di hari tertentu
        tugas_hari_aktif = {}
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            for hari in self.list_hari:
                tugas_hari_aktif[(t_id, hari)] = self.model.NewBoolVar(f"aktif_t_{t_id}_{hari}")
                
                # Hubungkan dengan slot jam
                self.model.AddMaxEquality(
                    tugas_hari_aktif[(t_id, hari)],
                    [self.variables[(t_id, hari, jam)] for jam in self.jam_per_hari[hari]]
                )

        # =====================================================
        # HARD CONSTRAINT MODEL
        # =====================================================

        # Rule 1: Setiap sub-tugas wajib dipenuhi sesuai alokasi JP-nya
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            self.model.Add(
                sum(self.variables[(t_id, hari, jam)] for hari in self.list_hari for jam in self.jam_per_hari[hari]) == t["jp"]
            )
            
            # Constraint: 1 sub-tugas hanya boleh diselesaikan penuh dalam 1 hari tunggal (Blok Utuh)
            self.model.Add(sum(tugas_hari_aktif[(t_id, hari)] for hari in self.list_hari) == 1)

        # Rule 2: Satu Rombel tidak boleh menerima > 1 guru di jam yang sama
        for rombel in self.list_rombel:
            tugas_rombel = [t["id_tugas"] for t in self.tugas_mengajar if t["rombel"] == rombel]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(
                        sum(self.variables[(t_id, hari, jam)] for t_id in tugas_rombel) <= 1 # <-- Sudah Diperbaiki
                    )

        # Rule 3: Satu Guru tidak boleh mengajar > 1 kelas di jam yang sama
        for guru in self.list_guru:
            tugas_guru = [t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(
                        sum(self.variables[(t_id, hari, jam)] for t_id in tugas_guru) <= 1
                    )

        # Rule 4: Aturan Blok Jam Berurutan (No Gap didalam internal blok mapel)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            target_jp = t["jp"]
            if target_jp > 1:
                for hari in self.list_hari:
                    jam_hari = self.jam_per_hari[hari]
                    
                    # Logika sliding window untuk mengunci kedekatan jam pembelajaran
                    start_vars = []
                    for i in range(len(jam_hari) - target_jp + 1):
                        s_var = self.model.NewBoolVar(f"start_{t_id}_{hari}_{jam_hari[i]}")
                        start_vars.append(s_var)
                        
                        # Jika jendela ini dipilih, seluruh jam di range ini bernilai 1
                        for offset in range(target_jp):
                            self.model.Add(self.variables[(t_id, hari, jam_hari[i+offset])] == 1).OnlyEnforceIf(s_var)
                    
                    # Sub-tugas aktif di hari ini jika dan hanya jika salah satu jendela start dipilih
                    self.model.Add(sum(start_vars) == tugas_hari_aktif[(t_id, hari)])

        # Rule 5: Aturan Jam Khusus PJOK (M11) & Shift Mengajar
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    # Kondisi PJOK (Maksimal jam ke-6)
                    if mapel in self.mapel_pjok and jam > 6:
                        self.model.Add(self.variables[(t_id, hari, jam)] == 0)
                        
                    # Kondisi Shift Pagi Utama (Maksimal jam ke-6)
                    elif mapel in self.mapel_prioritas_pagi and jam > 6:
                        self.model.Add(self.variables[(t_id, hari, jam)] == 0)
                        
                    # Kondisi Shift Siang Utama (Hanya boleh jam 5 ke atas)
                    elif mapel in self.mapel_prioritas_siang and jam < 5:
                        self.model.Add(self.variables[(t_id, hari, jam)] == 0)

        # =====================================================
        # SOLVING PROSES
        # =====================================================
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_seconds
        
        status = solver.Solve(self.model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("✓ HORE! AI berhasil menemukan solusi jadwal yang valid!")
            # Proses konversi self.variables menjadi DataFrame output dapat ditaruh disini
            return True
        else:
            print("× AI tetap tidak menemukan solusi. Periksa batasan ruang / total jam guru.")
            return False
