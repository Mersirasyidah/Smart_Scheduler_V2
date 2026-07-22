import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df
        self.rombel_df = rombel_df
        self.mengajar_df = mengajar_df
        self.mapel_df = mapel_df
        self.slot_df = slot_df

        # Bersihkan nama kolom dari whitespace
        for df in [
            self.guru_df,
            self.rombel_df,
            self.mengajar_df,
            self.mapel_df,
            self.slot_df,
        ]:
            df.columns = [str(c).strip() for c in df.columns]

    def _get_col(self, df, possible_names):
        """Mencari nama kolom secara fleksibel."""
        for name in possible_names:
            for col in df.columns:
                c_clean = str(col).strip().lower().replace("_", " ")
                n_clean = name.lower().replace("_", " ")
                if c_clean == n_clean:
                    return col
        return df.columns[0]

    def _solve_skenario(self, timeout_sec, strict_mgmp=True):
        model = cp_model.CpModel()

        # Deteksi Kolom Fleksibel
        col_rombel_id = self._get_col(
            self.rombel_df,
            ["ID_Rombel", "ID Rombel", "Rombel", "Kelas", "Kelas / Rombel"],
        )
        col_mengajar_rombel = self._get_col(
            self.mengajar_df,
            ["ID_Rombel", "ID Rombel", "Rombel", "Kelas", "Kelas / Rombel"],
        )
        col_mengajar_guru = self._get_col(
            self.mengajar_df, ["ID_Guru", "ID Guru", "Guru", "Nama Guru"]
        )
        col_mengajar_mapel = self._get_col(
            self.mengajar_df,
            ["ID_Mapel", "ID Mapel", "Mapel", "Mata Pelajaran"],
        )
        col_mengajar_jp = self._get_col(
            self.mengajar_df, ["Beban_JP", "Beban JP", "JP", "Jumlah_JP"]
        )

        rombel_list = (
            self.rombel_df[col_rombel_id]
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        # Filter Slot yang Berjenis 'PEMBELAJARAN'
        col_jenis = next(
            (c for c in self.slot_df.columns if c.lower() == "jenis"), None
        )
        if col_jenis:
            slot_pemb = self.slot_df[
                self.slot_df[col_jenis].astype(str).str.strip().str.upper()
                == "PEMBELAJARAN"
            ]
        else:
            slot_pemb = self.slot_df

        col_slot_hari = self._get_col(self.slot_df, ["Hari"])
        col_slot_jam = self._get_col(
            self.slot_df, ["Jam_Ke", "Jam Ke", "Jam"]
        )

        hari_list = (
            slot_pemb[col_slot_hari].astype(str).str.strip().unique().tolist()
        )

        slot_tuples = []
        for _, row in slot_pemb.iterrows():
            slot_tuples.append(
                (str(row[col_slot_hari]).strip(), int(row[col_slot_jam]))
            )
        slot_tuples = sorted(list(set(slot_tuples)))

        # Variabel Keputusan
        X = {}
        tugas_info = []

        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row[col_mengajar_rombel]).strip()
            guru = str(row[col_mengajar_guru]).strip()
            mapel = str(row[col_mengajar_mapel]).strip()
            jp = int(row[col_mengajar_jp])

            tugas_info.append(
                {
                    "idx": idx,
                    "rombel": rombel,
                    "guru": guru,
                    "mapel": mapel,
                    "jp": jp,
                }
            )

            for h, j in slot_tuples:
                X[(idx, h, j)] = model.NewBoolVar(f"x_{idx}_{h}_{j}")

        # -------------------------------------------------------------
        # CONSTRAINT 1: Terpenuhi Seluruh Beban JP Sesuai Sheet Mengajar
        # -------------------------------------------------------------
        for t in tugas_info:
            model.Add(
                sum(X[(t["idx"], h, j)] for h, j in slot_tuples) == t["jp"]
            )

        # -------------------------------------------------------------
        # CONSTRAINT 2: Maksimal 1 Mapel per Slot per Rombel
        # -------------------------------------------------------------
        for r in rombel_list:
            tugas_rombel = [t["idx"] for t in tugas_info if t["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(idx, h, j)] for idx in tugas_rombel) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 3: Guru Tidak Bentrok Mengajar di 2 Rombel
        # -------------------------------------------------------------
        col_guru_id = self._get_col(
            self.guru_df, ["ID_Guru", "ID Guru", "Guru", "Nama Guru"]
        )
        guru_list = (
            self.guru_df[col_guru_id].astype(str).str.strip().unique().tolist()
        )
        for g in guru_list:
            tugas_guru = [t["idx"] for t in tugas_info if t["guru"] == g]
            for h, j in slot_tuples:
                model.Add(sum(X[(idx, h, j)] for idx in tugas_guru) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 4: MAX 2 JP PER HARI & BLOK JAM BERURUTAN
        # -------------------------------------------------------------
        for r in rombel_list:
            mapel_in_rombel = set(
                t["mapel"] for t in tugas_info if t["rombel"] == r
            )
            for m in mapel_in_rombel:
                tugas_m = [
                    t["idx"]
                    for t in tugas_info
                    if t["rombel"] == r and t["mapel"] == m
                ]
                for h in hari_list:
                    j_in_h = sorted(
                        [sj for (sh, sj) in slot_tuples if sh == h]
                    )

                    # Total JP per hari untuk mapel ini max 2
                    day_sum = sum(
                        X[(idx, h, j)]
                        for idx in tugas_m
                        for j in j_in_h
                        if (idx, h, j) in X
                    )
                    model.Add(day_sum <= 2)

                    # Jika 2 JP dalam sehari, pastikan jamnya BERURUTAN (Blok Continuous)
                    # Variabel penanda apakah mapel M mengajar 2 JP pada hari H
                    is_2jp = model.NewBoolVar(f"is2jp_{r}_{m}_{h}")
                    model.Add(day_sum == 2).OnlyEnforceIf(is_2jp)
                    model.Add(day_sum != 2).OnlyEnforceIf(is_2jp.Not())

                    # Cari pasangan jam berurutan
                    pair_vars = []
                    for k in range(len(j_in_h) - 1):
                        j1 = j_in_h[k]
                        j2 = j_in_h[k + 1]
                        if j2 == j1 + 1:  # Hanya jika jam benar-benar berurutan
                            p_var = model.NewBoolVar(f"pair_{r}_{m}_{h}_{j1}")
                            # p_var = 1 jika kedua jam dipilih
                            sum_pair = sum(
                                X[(idx, h, j1)] + X[(idx, h, j2)]
                                for idx in tugas_m
                            )
                            model.Add(sum_pair == 2).OnlyEnforceIf(p_var)
                            model.Add(sum_pair != 2).OnlyEnforceIf(p_var.Not())
                            pair_vars.append(p_var)

                    if pair_vars:
                        # Jika dapat 2 JP di hari tersebut, minimal 1 pasangan jam berurutan aktif
                        model.Add(sum(pair_vars) >= 1).OnlyEnforceIf(is_2jp)

        # -------------------------------------------------------------
        # CONSTRAINT 5: ATURAN KHUSUS MAPEL M08 (WAJIB JAM 1 S.D 4)
        # -------------------------------------------------------------
        for t in tugas_info:
            if t["mapel"].upper() == "M08":
                for h, j in slot_tuples:
                    if j > 4:
                        model.Add(X[(t["idx"], h, j)] == 0)

        # -------------------------------------------------------------
        # CONSTRAINT 6: MGMP GURU
        # -------------------------------------------------------------
        col_mgmp = self._get_col(
            self.guru_df, ["Hari_MGMP", "Hari MGMP", "MGMP"]
        )
        if strict_mgmp and col_mgmp in self.guru_df.columns:
            for _, row in self.guru_df.iterrows():
                g_id = str(row[col_guru_id]).strip()
                mgmp_day = (
                    str(row[col_mgmp]).strip()
                    if pd.notna(row.get(col_mgmp))
                    else ""
                )

                if mgmp_day and mgmp_day.lower() != "nan":
                    tugas_g = [
                        t["idx"] for t in tugas_info if t["guru"] == g_id
                    ]
                    for h, j in slot_tuples:
                        if h.lower() == mgmp_day.lower() and j > 4:
                            for idx in tugas_g:
                                model.Add(X[(idx, h, j)] == 0)

        # EXECUTE SOLVER
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(timeout_sec)
        solver.parameters.num_search_workers = 4

        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            results = []
            for t in tugas_info:
                for h, j in slot_tuples:
                    if solver.Value(X[(t["idx"], h, j)]) == 1:
                        results.append(
                            {
                                "Hari": h,
                                "Jam_Ke": j,
                                "ID_Rombel": t["rombel"],
                                "ID_Guru": t["guru"],
                                "ID_Mapel": t["mapel"],
                            }
                        )

            df_res = pd.DataFrame(results)
            if not df_res.empty:
                df_res = df_res.sort_values(
                    by=["ID_Rombel", "Hari", "Jam_Ke"]
                ).reset_index(drop=True)

            # Laporan Total JP Terjadwal Akurat
            df_laporan = (
                df_res.groupby("ID_Guru", as_index=False)
                .size()
                .rename(columns={"size": "Total_JP_Terjadwal"})
            )

            return True, df_res, df_laporan
        else:
            return False, pd.DataFrame(), pd.DataFrame()

    def solve_with_fallback(self, timeout_total=180, progress_callback=None):
        if progress_callback:
            progress_callback(
                "Mencari jadwal optimal (Max 2 JP/hari blok berurutan & M08 Jam 1-4)..."
            )

        t_stage = max(30, int(timeout_total * 0.7))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t_stage, strict_mgmp=True
        )

        if success:
            return (
                True,
                df_res,
                df_lap,
                "Skenario Optimal (MGMP Strict, Blok Berurutan & M08 Jam 1-4)",
            )

        if progress_callback:
            progress_callback("Mencoba relaksasi jam MGMP guru...")

        t_rem = max(30, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t_rem, strict_mgmp=False
        )

        if success:
            return (
                True,
                df_res,
                df_lap,
                "Skenario Relaksasi (MGMP Disesuaikan, M08 Jam 1-4)",
            )

        return False, pd.DataFrame(), pd.DataFrame(), "Solver Tidak Menemukan Solusi"

    def generate(self, timeout=120):
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout
        )
        return df_hasil, df_laporan
