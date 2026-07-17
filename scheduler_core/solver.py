import pandas as pd
from ortools.sat.python import cp_model


class SchedulerSolver:

    def __init__(self, scheduler):

        self.scheduler = scheduler
        self.model = cp_model.CpModel()

        # =====================================================
        # DATA MASTER
        # =====================================================

        self.guru = scheduler.guru.copy()
        self.rombel = scheduler.rombel.copy()
        self.mengajar = scheduler.mengajar.copy()
        self.mapel = scheduler.mapel.copy()
        self.slot = scheduler.slot.copy()

        # =====================================================
        # LIST DATA
        # =====================================================

        self.list_guru = self.guru["ID_Guru"].tolist()
        self.list_rombel = self.rombel["ID_Rombel"].tolist()
        self.list_mapel = self.mapel["ID_Mapel"].tolist()
        self.list_hari = self.slot["Hari"].unique().tolist()

        # =====================================================
        # JAM PER HARI
        # =====================================================

        self.jam_per_hari = {}

        for hari in self.list_hari:

            self.jam_per_hari[hari] = sorted(
                self.slot[
                    self.slot["Hari"] == hari
                ]["Jam_Ke"].tolist()
            )

        # =====================================================
        # VARIABEL SOLVER
        # =====================================================

        self.variables = {}
        self.is_active_day = {}
        self.penalties = []

        # =====================================================
        # KATEGORI MAPEL
        # =====================================================

        self.mapel_prioritas_pagi = set()
        self.mapel_pjok = set()
        self.mapel_prioritas_siang = set()
        self.mapel_normal = set()

        # =====================================================
        # MEMBACA KATEGORI DARI EXCEL & DETEKSI OTOMATIS
        # =====================================================

        if "Kategori" in self.mapel.columns:
            for _, row in self.mapel.iterrows():
                kategori = str(row["Kategori"]).strip().upper()
                kode = str(row["ID_Mapel"]).strip().upper()

                # Pengecekan eksplisit untuk kode M11 sebagai PJOK
                if kode == "M11" or kategori == "PJOK":
                    self.mapel_pjok.add(row["ID_Mapel"])
                elif kategori == "PRIORITAS_PAGI":
                    self.mapel_prioritas_pagi.add(row["ID_Mapel"])
                elif kategori == "SIANG":
                    self.mapel_prioritas_siang.add(row["ID_Mapel"])
                else:
                    self.mapel_normal.add(row["ID_Mapel"])
        else:
            # =================================================
            # FALLBACK OTOMATIS BERDASARKAN KODE / NAMA MAPEL
            # =================================================
            for _, row in self.mapel.iterrows():
                kode = str(row["ID_Mapel"]).strip().upper()
                nama = ""
                if "Nama_Mapel" in self.mapel.columns:
                    nama = str(row["Nama_Mapel"]).strip().upper()

                teks = kode + " " + nama

                # ================================
                # PJOK (M11 didahulukan)
                # ================================
                if (
                    kode == "M11" 
                    or "PJOK" in teks 
                    or "PENJAS" in teks 
                    or "PENYAS" in teks
                ):
                    self.mapel_pjok.add(row["ID_Mapel"])

                # ================================
                # PRIORITAS PAGI
                # ================================
                elif (
                    "MAT" in teks
                    or "MATEMATIKA" in teks
                    or "IPA" in teks
                    or "BAHASA INDONESIA" in teks
                    or "INDONESIA" in teks
                    or "BAHASA INGGRIS" in teks
                    or "INGGRIS" in teks
                ):
                    self.mapel_prioritas_pagi.add(row["ID_Mapel"])

                # ================================
                # SIANG
                # ================================
                elif (
                    "PRAKARYA" in teks
                    or "SENI" in teks
                    or "SBK" in teks
                    or "BAHASA JAWA" in teks
                ):
                    self.mapel_prioritas_siang.add(row["ID_Mapel"])

                else:
                    self.mapel_normal.add(row["ID_Mapel"])

        # =====================================================
        # INFORMASI
        # =====================================================

        print("=" * 60)
        print("MAPEL PRIORITAS PAGI")
        print(sorted(self.mapel_prioritas_pagi))
        print()
        print("MAPEL PJOK")
        print(sorted(self.mapel_pjok))
        print()
        print("MAPEL PRIORITAS SIANG")
        print(sorted(self.mapel_prioritas_siang))
        print()
        print("MAPEL NORMAL")
        print(sorted(self.mapel_normal))
        print("=" * 60)

    # =====================================================
    # RUN SOLVER
    # =====================================================

    def run_solver(self, timeout_seconds=120):

        print("=" * 60)
        print("MEMBANGUN MODEL PENJADWALAN")
        print("=" * 60)

        # =====================================================
        # MEMBUAT VARIABEL KEPUTUSAN
        # =====================================================

        for _, row in self.mengajar.iterrows():

            guru = row["ID_Guru"]
            rombel = row["ID_Rombel"]
            mapel = row["ID_Mapel"]

            for hari in self.list_hari:

                for jam in self.jam_per_hari[hari]:

                    self.variables[(guru, rombel, mapel, hari, jam)] = (
                        self.model.NewBoolVar(
                            f"x_{guru}_{rombel}_{mapel}_{hari}_{jam}"
                        )
                    )

                self.is_active_day[(guru, rombel, mapel, hari)] = (
                    self.model.NewBoolVar(
                        f"aktif_{guru}_{rombel}_{mapel}_{hari}"
                    )
                )

                self.model.AddMaxEquality(
                    self.is_active_day[(guru, rombel, mapel, hari)],
                    [
                        self.variables[(guru, rombel, mapel, hari, jam)]
                        for jam in self.jam_per_hari[hari]
                    ]
                )

        print("✓ Variabel berhasil dibuat")

        # =====================================================
        # HARD CONSTRAINT
        # TOTAL JP WAJIB TERPENUHI
        # =====================================================

        print("Memasang Hard Constraint Total JP")

        for _, row in self.mengajar.iterrows():

            guru = row["ID_Guru"]
            rombel = row["ID_Rombel"]
            mapel = row["ID_Mapel"]

            target_jp = int(row[self.scheduler.col_jp])

            self.model.Add(
                sum(
                    self.variables[(guru, rombel, mapel, hari, jam)]
                    for hari in self.list_hari
                    for jam in self.jam_per_hari[hari]
                )
                == target_jp
            )

        print("✓ Total JP selesai")

        # =====================================================
        # HARD CONSTRAINT
        # SATU KELAS SATU MAPEL
        # =====================================================

        print("Memasang Hard Constraint Kelas")

        for rombel in self.list_rombel:

            data_rombel = self.mengajar[
                self.mengajar["ID_Rombel"] == rombel
            ]

            for hari in self.list_hari:

                for jam in self.jam_per_hari[hari]:

                    aktif = []

                    for _, row in data_rombel.iterrows():

                        aktif.append(
                            self.variables[
                                (
                                    row["ID_Guru"],
                                    rombel,
                                    row["ID_Mapel"],
                                    hari,
                                    jam
                                )
                            ]
                        )

                    self.model.Add(sum(aktif) <= 1)

        print("✓ Constraint Kelas selesai")

        # =====================================================
        # HARD CONSTRAINT
        # SATU GURU SATU KELAS
        # =====================================================

        print("Memasang Hard Constraint Guru")

        for guru in self.list_guru:

            data_guru = self.mengajar[
                self.mengajar["ID_Guru"] == guru
            ]

            for hari in self.list_hari:

                for jam in self.jam_per_hari[hari]:

                    aktif = []

                    for _, row in data_guru.iterrows():

                        aktif.append(
                            self.variables[
                                (
                                    guru,
                                    row["ID_Rombel"],
                                    row["ID_Mapel"],
                                    hari,
                                    jam
                                )
                            ]
                        )

                    self.model.Add(sum(aktif) <= 1)

        print("✓ Constraint Guru selesai")

        # =====================================================
        # HARD CONSTRAINT
        # MAPEL PRIORITAS PAGI
        # =====================================================

        print("Memasang Prioritas Mapel Pagi")

        for (guru, rombel, mapel, hari, jam), var in self.variables.items():

            if mapel not in self.mapel_prioritas_pagi:
                continue

            if jam >= 5:
                self.model.Add(var == 0)

        print("✓ Prioritas Mapel selesai")

        # =====================================================
        # HARD CONSTRAINT
        # PJOK
        # =====================================================

        print("Memasang Constraint PJOK")

        pjok_rows = self.mengajar[
            self.mengajar["ID_Mapel"].isin(self.mapel_pjok)
        ].copy()

        pjok_rows = pjok_rows.sort_values("ID_Rombel")

        rombel_pagi = set(
            pjok_rows["ID_Rombel"].unique()[:10]
        )

        rombel_siang = set(
            pjok_rows["ID_Rombel"].unique()[10:]
        )

        print("PJOK PAGI :", sorted(rombel_pagi))
        print("PJOK SIANG:", sorted(rombel_siang))

        for (guru, rombel, mapel, hari, jam), var in self.variables.items():

            if mapel not in self.mapel_pjok:
                continue

            if jam > 6:
                self.model.Add(var == 0)

            if rombel in rombel_pagi:

                if str(hari).upper() == "SENIN":

                    if jam not in [2, 3, 4]:
                        self.model.Add(var == 0)

                else:

                    if jam not in [1, 2, 3]:
                        self.model.Add(var == 0)

            elif rombel in rombel_siang:

                if jam not in [4, 5, 6]:
                    self.model.Add(var == 0)

        print("✓ Constraint PJOK selesai")

        # =====================================================
        # PJOK HARUS BERURUTAN
        # =====================================================

        print("Memasang Constraint Blok PJOK")

        for _, row in pjok_rows.iterrows():

            guru = row["ID_Guru"]
            rombel = row["ID_Rombel"]
            mapel = row["ID_Mapel"]

            target_jp = int(row[self.scheduler.col_jp])

            if target_jp <= 1:
                continue

            for hari in self.list_hari:

                daftar = []

                for jam in self.jam_per_hari[hari]:

                    daftar.append(
                        self.variables[
                            (
                                guru,
                                rombel,
                                mapel,
                                hari,
                                jam
                            )
                        ]
                    )

                self.model.Add(sum(daftar) <= target_jp)

        print("✓ Blok PJOK selesai")

        # =====================================================
        # HARD CONSTRAINT
        # BLOK JP BERURUTAN
        # =====================================================

        print("Memasang Constraint Blok Jam Berurutan")

        for _, row in self.mengajar.iterrows():

            guru = row["ID_Guru"]
            rombel = row["ID_Rombel"]
            mapel = row["ID_Mapel"]

            target_jp = int(row[self.scheduler.col_jp])

            if target_jp <= 1:
                continue

            for hari in self.list_hari:

                jam_hari = sorted(self.jam_per_hari[hari])

                start_block = {}

                for awal in jam_hari:

                    if awal + target_jp - 1 > max(jam_hari):
                        continue

                    start_block[awal] = self.model.NewBoolVar(
                        f"start_{guru}_{rombel}_{mapel}_{hari}_{awal}"
                    )

                if start_block:
                    self.model.Add(
                        sum(start_block.values()) <= 1
                    )

                for awal, start_var in start_block.items():

                    for offset in range(target_jp):

                        jam = awal + offset

                        self.model.Add(
                            self.variables[
                                (
                                    guru,
                                    rombel,
                                    mapel,
                                    hari,
                                    jam
                                )
                            ] == 1
                        ).OnlyEnforceIf(start_var)

                semua_start = list(start_block.values())

                if semua_start:

                    for jam in jam_hari:

                        kandidat = []

                        for awal, start_var in start_block.items():

                            if awal <= jam <= awal + target_jp - 1:
                                kandidat.append(start_var)

                        if kandidat:
                            self.model.Add(
                                self.variables[
                                    (
                                        guru,
                                        rombel,
                                        mapel,
                                        hari,
                                        jam
                                    )
                                ]
                                <= sum(kandidat)
                            )

        print("✓ Constraint Blok Jam selesai")

        # =====================================================
        # HARD CONSTRAINT
        # MAPEL HANYA SATU BLOK DALAM SATU HARI
        # =====================================================

        print("Memasang Constraint Satu Blok Per Hari")

        for _, row in self.mengajar.iterrows():

            guru = row["ID_Guru"]
            rombel = row["ID_Rombel"]
            mapel = row["ID_Mapel"]

            target_jp = int(row[self.scheduler.col_jp])

            for hari in self.list_hari:

                vars_hari = [
                    self.variables[
                        (
                            guru,
                            rombel,
                            mapel,
                            hari,
                            jam
                        )
                    ]
                    for jam in self.jam_per_hari[hari]
                ]

                self.model.Add(
                    sum(vars_hari) <= target_jp
                )

        print("✓ Constraint Satu Blok selesai")

        # =====================================================
        # HARD CONSTRAINT
        # TIDAK BOLEH ADA GAP
        # =====================================================

        print("Memasang Constraint No Gap")

        for _, row in self.mengajar.iterrows():

            guru = row["ID_Guru"]
            rombel = row["ID_Rombel"]
            mapel = row["ID_Mapel"]

            for hari in self.list_hari:

                jam_hari = sorted(self.jam_per_hari[hari])

                if len(jam_hari) < 3:
                    continue

                for i in range(1, len(jam_hari)-1):

                    kiri = jam_hari[i-1]
                    tengah = jam_hari[i]
                    kanan = jam_hari[i+1]

                    self.model.Add(
                        self.variables[
                            (
                                guru,
                                rombel,
                                mapel,
                                hari,
                                kiri
                            )
                        ]
                        +
                        self.variables[
                            (
                                guru,
                                rombel,
                                mapel,
                                hari,
                                kanan
                            )
                        ]
                        -
                        self.variables[
                            (
                                guru,
                                rombel,
                                mapel,
                                hari,
                                tengah
                            )
                        ]
                        <= 1
                    )

        print("✓ Constraint No Gap selesai")
