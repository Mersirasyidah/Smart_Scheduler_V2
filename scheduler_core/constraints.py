# scheduler_core/constraints.py


class ConstraintBuilder:

    def __init__(self, solver_engine):
        self.se = solver_engine
        self.model = solver_engine.model
        self.x = solver_engine.variables
        self.tugas_hari_aktif = solver_engine.tugas_hari_aktif

        self.tugas_mengajar = solver_engine.tugas_mengajar
        self.list_hari = solver_engine.list_hari
        self.jam_per_hari = solver_engine.jam_per_hari
        self.list_guru = solver_engine.list_guru
        self.list_rombel = solver_engine.list_rombel
        self.list_mapel = solver_engine.list_mapel

    def apply_all(self, max_jam_mgmp_nongtt=3):
        """Menjalankan seluruh batasan (hard & soft)"""
        self.apply_hard_constraints(max_jam_mgmp_nongtt)
        self.apply_soft_constraints()

    def apply_hard_constraints(self, max_jam_mgmp_nongtt):
        # 1. Total JP & Pembagian per Hari
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            rombel = t["rombel"]

            # Total jam mengajar harus sama dengan JP
            self.model.Add(
                sum(
                    self.x[(t_id, hari, jam)]
                    for hari in self.list_hari
                    for jam in self.jam_per_hari[hari]
                )
                == t["jp"]
            )

            # Setiap blok tugas hanya aktif di 1 hari
            self.model.Add(
                sum(
                    self.tugas_hari_aktif[(t_id, hari)]
                    for hari in self.list_hari
                )
                == 1
            )

            # Agama M01 Kunci Hari Kamis untuk Rombel tertentu
            if mapel == "M01" and rombel in ["7A", "8A", "8C", "9A"]:
                kamis_key = next(
                    (
                        h
                        for h in self.list_hari
                        if h.strip().lower() == "kamis"
                    ),
                    None,
                )
                if kamis_key:
                    self.model.Add(
                        self.tugas_hari_aktif[(t_id, kamis_key)] == 1
                    )

            # PJOK Jam Maksimal Jam ke-6
            if mapel in self.se.mapel_pjok:
                for hari in self.list_hari:
                    for jam in self.jam_per_hari[hari]:
                        if jam > 6:
                            self.model.Add(self.x[(t_id, hari, jam)] == 0)

        # 2. Aturan MGMP: GTT MUTLAK LIBUR, NON-GTT FLEKSIBEL (Penalti jika > max_jam)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            guru = t["guru"]
            mapel = t["mapel"]

            hari_mgmp_str = self.se.guru_mgmp_dict.get(
                guru
            ) or self.se.mapel_mgmp_dict.get(mapel)

            if hari_mgmp_str:
                hari_mgmp_match = next(
                    (
                        h
                        for h in self.list_hari
                        if h.strip().lower() == hari_mgmp_str.lower()
                    ),
                    None,
                )

                if hari_mgmp_match:
                    # GTT: Mutlak Libur
                    if guru in self.se.guru_gtt_set:
                        self.model.Add(
                            self.tugas_hari_aktif[(t_id, hari_mgmp_match)] == 0
                        )

                    # NON-GTT: Beri Penalti Jika Lebih dari max_jam_mgmp_nongtt
                    else:
                        for jam in self.jam_per_hari[hari_mgmp_match]:
                            if jam > max_jam_mgmp_nongtt:
                                self.se.penalties.append(
                                    self.x[(t_id, hari_mgmp_match, jam)] * 5000
                                )

        # 3. Maksimal 5 Mapel per Hari per Rombel
        for rombel in self.list_rombel:
            for hari in self.list_hari:
                mapel_aktif_hari = []
                for mapel in self.list_mapel:
                    tugas_mapel = [
                        t["id_tugas"]
                        for t in self.tugas_mengajar
                        if t["rombel"] == rombel and t["mapel"] == mapel
                    ]
                    if tugas_mapel:
                        is_active = self.model.NewBoolVar(
                            f"active_{rombel}_{mapel}_{hari}"
                        )
                        self.model.AddMaxEquality(
                            is_active,
                            [
                                self.tugas_hari_aktif[(t_id, hari)]
                                for t_id in tugas_mapel
                            ],
                        )
                        mapel_aktif_hari.append(is_active)

                if mapel_aktif_hari:
                    self.model.Add(sum(mapel_aktif_hari) <= 5)

        # 4. Maksimal 1 Pertemuan per Hari untuk Mapel yang Sama
        for rombel in self.list_rombel:
            for mapel in self.list_mapel:
                tugas_sama = [
                    t["id_tugas"]
                    for t in self.tugas_mengajar
                    if t["rombel"] == rombel and t["mapel"] == mapel
                ]
                if len(tugas_sama) > 1:
                    for hari in self.list_hari:
                        self.model.Add(
                            sum(
                                self.tugas_hari_aktif[(t_id, hari)]
                                for t_id in tugas_sama
                            )
                            <= 1
                        )

        # 5. Mencegah Bentrok Rombel
        for rombel in self.list_rombel:
            tugas_rombel = [
                t["id_tugas"]
                for t in self.tugas_mengajar
                if t["rombel"] == rombel
            ]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(
                        sum(
                            self.x[(t_id, hari, jam)] for t_id in tugas_rombel
                        )
                        <= 1
                    )

        # 6. Mencegah Bentrok Guru
        for guru in self.list_guru:
            tugas_guru = [
                t["id_tugas"] for t in self.tugas_mengajar if t["guru"] == guru
            ]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    self.model.Add(
                        sum(self.x[(t_id, hari, jam)] for t_id in tugas_guru)
                        <= 1
                    )

        # 7. Blok Jam Berurutan (Sliding Window Exact)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            target_jp = t["jp"]
            if target_jp > 1:
                for hari in self.list_hari:
                    jam_hari = self.jam_per_hari[hari]
                    start_vars = []
                    num_windows = len(jam_hari) - target_jp + 1

                    if num_windows > 0:
                        for i in range(num_windows):
                            s_var = self.model.NewBoolVar(
                                f"start_{t_id}_{hari}_{jam_hari[i]}"
                            )
                            start_vars.append(s_var)
                            for offset in range(target_jp):
                                self.model.Add(
                                    self.x[
                                        (t_id, hari, jam_hari[i + offset])
                                    ]
                                    == 1
                                ).OnlyEnforceIf(s_var)
                        self.model.Add(
                            sum(start_vars)
                            == self.tugas_hari_aktif[(t_id, hari)]
                        )
                    else:
                        self.model.Add(
                            self.tugas_hari_aktif[(t_id, hari)] == 0
                        )

    def apply_soft_constraints(self):
        # Penalti PJOK di atas Jam ke-3 (Siang Hari)
        for t in self.tugas_mengajar:
            t_id = t["id_tugas"]
            mapel = t["mapel"]
            for hari in self.list_hari:
                for jam in self.jam_per_hari[hari]:
                    if mapel in self.se.mapel_pjok and jam > 3:
                        self.se.penalties.append(
                            self.x[(t_id, hari, jam)] * 500
                        )
