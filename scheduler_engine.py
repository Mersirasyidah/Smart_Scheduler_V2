import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df
        self.rombel_df = rombel_df
        self.mengajar_df = mengajar_df
        self.mapel_df = mapel_df
        self.slot_df = slot_df

        # Clean whitespace from column names
        for df in [
            self.guru_df,
            self.rombel_df,
            self.mengajar_df,
            self.mapel_df,
            self.slot_df,
        ]:
            df.columns = [str(c).strip() for c in df.columns]

    def _get_col(self, df, possible_names):
        """Finds column name flexibly."""
        for name in possible_names:
            for col in df.columns:
                c_clean = str(col).strip().lower().replace("_", " ")
                n_clean = name.lower().replace("_", " ")
                if c_clean == n_clean:
                    return col
        return df.columns[0]

    def _parse_blok(self, val_blok, total_jp):
        """Memecah nilai kolom 'Blok' (misal '2,2' atau '3,2') menjadi list durasi sesi."""
        if pd.isna(val_blok) or not str(val_blok).strip():
            return [total_jp]

        s_val = str(val_blok).replace(";", ",").replace("-", ",")
        parts = [p.strip() for p in s_val.split(",") if p.strip()]

        durations = []
        for p in parts:
            try:
                dur = int(p)
                if dur > 0:
                    durations.append(dur)
            except ValueError:
                pass

        if sum(durations) == total_jp and len(durations) > 0:
            return durations

        # Fallback jika total tidak cocok: pecah standar 2 JP-an
        res = []
        rem = total_jp
        while rem > 0:
            take = min(2, rem)
            res.append(take)
            rem -= take
        return res

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

        col_mapel_id = self._get_col(
            self.mapel_df, ["ID_Mapel", "ID Mapel", "Mapel"]
        )
        col_mapel_blok = next(
            (
                c
                for c in self.mapel_df.columns
                if str(c).strip().lower() == "blok"
            ),
            None,
        )

        # Mapping Mapel ke Skema Blok
        blok_map = {}
        if col_mapel_blok:
            for _, r_m in self.mapel_df.iterrows():
                m_id = str(r_m[col_mapel_id]).strip()
                blok_map[m_id] = r_m[col_mapel_blok]

        rombel_list = (
            self.rombel_df[col_rombel_id]
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        # Slot Pembelajaran
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

        # Break Tugas Mengajar menjadi Sesi Berdasarkan Kolom Blok
        sessions = []
        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row[col_mengajar_rombel]).strip()
            guru = str(row[col_mengajar_guru]).strip()
            mapel = str(row[col_mengajar_mapel]).strip()
            total_jp = int(row[col_mengajar_jp])

            raw_blok = blok_map.get(mapel, None)
            durations = self._parse_blok(raw_blok, total_jp)

            for s_idx, dur in enumerate(durations):
                sessions.append(
                    {
                        "session_id": f"{idx}_s{s_idx}",
                        "tugas_idx": idx,
                        "rombel": rombel,
                        "guru": guru,
                        "mapel": mapel,
                        "duration": dur,
                    }
                )

        # Decision Variables
        # S[(s_id, h, j)] = 1 jika Sesi s_id MULAI di Hari h pada Jam Ke j
        S = {}
        # X[(s_id, h, j)] = 1 jika Sesi s_id MENEMPATI Hari h pada Jam Ke j
        X = {}

        for s in sessions:
            s_id = s["session_id"]
            dur = s["duration"]
            for h, j in slot_tuples:
                X[(s_id, h, j)] = model.NewBoolVar(f"x_{s_id}_{h}_{j}")

            # Variabel Waktu Mulai Sesi
            for h in hari_list:
                j_in_h = sorted([sj for (sh, sj) in slot_tuples if sh == h])
                for j in j_in_h:
                    S[(s_id, h, j)] = model.NewBoolVar(f"s_{s_id}_{h}_{j}")

                    # Cek apakah durasi muat secara berurutan mulai dari jam j
                    valid_block = True
                    block_j = []
                    for k in range(dur):
                        if (j + k) in j_in_h:
                            block_j.append(j + k)
                        else:
                            valid_block = False
                            break

                    if not valid_block:
                        model.Add(S[(s_id, h, j)] == 0)
                    else:
                        # Jika Sesi dimulai di (h, j), maka mengunci jam j s.d. j+dur-1
                        for bj in block_j:
                            model.Add(
                                X[(s_id, h, bj)] == 1
                            ).OnlyEnforceIf(S[(s_id, h, j)])

        # -------------------------------------------------------------
        # CONSTRAINT 1: Setiap Sesi Harus Ditempatkan Tepat 1 Kali
        # -------------------------------------------------------------
        for s in sessions:
            s_id = s["session_id"]
            model.Add(
                sum(
                    S[(s_id, h, j)]
                    for h in hari_list
                    for j in [sj for (sh, sj) in slot_tuples if sh == h]
                )
                == 1
            )

        # -------------------------------------------------------------
        # CONSTRAINT 2: Maksimal 1 Sesi per Slot per Rombel
        # -------------------------------------------------------------
        for r in rombel_list:
            s_ids_r = [s["session_id"] for s in sessions if s["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_r) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 3: Guru Tidak Bentrok Mengajar
        # -------------------------------------------------------------
        col_guru_id = self._get_col(
            self.guru_df, ["ID_Guru", "ID Guru", "Guru", "Nama Guru"]
        )
        guru_list = (
            self.guru_df[col_guru_id].astype(str).str.strip().unique().tolist()
        )
        for g in guru_list:
            s_ids_g = [s["session_id"] for s in sessions if s["guru"] == g]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_g) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 4: Sesi Berbeda dari Mapel Sama & Rombel Sama Tidak Boleh di Hari Sama
        # -------------------------------------------------------------
        for r in rombel_list:
            mapel_in_r = set(s["mapel"] for s in sessions if s["rombel"] == r)
            for m in mapel_in_r:
                s_m = [
                    s
                    for s in sessions
                    if s["rombel"] == r and s["mapel"] == m
                ]
                if len(s_m) > 1:
                    for h in hari_list:
                        # Maksimal 1 sesi per hari untuk mapel yang sama
                        j_in_h = [sj for (sh, sj) in slot_tuples if sh == h]
                        model.Add(
                            sum(
                                S[(s["session_id"], h, j)]
                                for s in s_m
                                for j in j_in_h
                            )
                            <= 1
                        )

        # -------------------------------------------------------------
        # CONSTRAINT 5: Aturan Khusus Mapel M08 (Hanya Jam Ke 1 s.d. 4)
        # -------------------------------------------------------------
        for s in sessions:
            if s["mapel"].upper() == "M08":
                s_id = s["session_id"]
                for h, j in slot_tuples:
                    if j > 4:
                        model.Add(X[(s_id, h, j)] == 0)

        # -------------------------------------------------------------
        # CONSTRAINT 6: MGMP Guru (Jam > 4 Kosong di Hari MGMP)
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
                    s_ids_g = [
                        s["session_id"] for s in sessions if s["guru"] == g_id
                    ]
                    for h, j in slot_tuples:
                        if h.lower() == mgmp_day.lower() and j > 4:
                            for s_id in s_ids_g:
                                model.Add(X[(s_id, h, j)] == 0)

        # EXECUTE SOLVER
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(timeout_sec)
        solver.parameters.num_search_workers = 4

        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            results = []
            for s in sessions:
                s_id = s["session_id"]
                for h, j in slot_tuples:
                    if solver.Value(X[(s_id, h, j)]) == 1:
                        results.append(
                            {
                                "Hari": h,
                                "Jam_Ke": j,
                                "ID_Rombel": s["rombel"],
                                "ID_Guru": s["guru"],
                                "ID_Mapel": s["mapel"],
                            }
                        )

            df_res = pd.DataFrame(results)
            if not df_res.empty:
                df_res = df_res.sort_values(
                    by=["ID_Rombel", "Hari", "Jam_Ke"]
                ).reset_index(drop=True)

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
                "Memproses skema Blok Mapel & menyusun jadwal optimal..."
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
                "Skenario Optimal (Sesuai Blok Mapel & MGMP Strict)",
            )

        if progress_callback:
            progress_callback("Mencoba relaksasi jam MGMP Guru...")

        t_rem = max(30, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t_rem, strict_mgmp=False
        )

        if success:
            return (
                True,
                df_res,
                df_lap,
                "Skenario Relaksasi (Sesuai Blok Mapel, MGMP Disesuaikan)",
            )

        return False, pd.DataFrame(), pd.DataFrame(), "Solver Tidak Menemukan Solusi"

    def generate(self, timeout=120):
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout
        )
        return df_hasil, df_laporan
