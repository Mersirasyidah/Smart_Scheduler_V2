import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df.copy()
        self.rombel_df = rombel_df.copy()
        self.mengajar_df = mengajar_df.copy()
        self.mapel_df = mapel_df.copy()
        self.slot_df = slot_df.copy()

        # Membersihkan spasi pada nama kolom
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

    def _parse_blok(self, val_blok, total_jp, mapel_code):
        """
        Aturan Blok Jam:
        1. Jika mapel_code == 'M05' dan total_jp == 3: Wajib dipecah [2, 1]
        2. Jika total_jp == 3 (selain M05): Wajib utuh [3]
        3. Untuk total_jp lainnya, baca kolom Blok pada Excel. Jika kosong, gunakan pecahan ideal.
        """
        mapel_clean = str(mapel_code).strip().upper()

        # Aturan Khusus M05 (3 JP -> dipecah 2, 1)
        if mapel_clean == "M05" and total_jp == 3:
            return [2, 1]

        # Aturan Umum Mapel 3 JP -> Langsung 3 JP Utuh
        if total_jp == 3 and (
            pd.isna(val_blok) or not str(val_blok).strip() or mapel_clean != "M05"
        ):
            # Jika di excel tidak ditulis beda secara spesifik, default 3 JP utuh
            if pd.isna(val_blok) or not str(val_blok).strip():
                return [3]

        # Pembacaan Nilai Kolom 'Blok' dari Sheet Mapel jika diisi manual
        if pd.notna(val_blok) and str(val_blok).strip():
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

            # Gunakan jika total penjumlahan blok di Excel persis sama dengan Beban JP
            if sum(durations) == total_jp and len(durations) > 0:
                return durations

        # Fallback Generator Otomatis jika kolom Blok kosong:
        # Misal 5 JP -> [3, 2], 4 JP -> [2, 2], 2 JP -> [2]
        if total_jp == 3:
            return [3]
        elif total_jp == 5:
            return [3, 2]
        elif total_jp == 4:
            return [2, 2]
        else:
            res = []
            rem = total_jp
            while rem > 0:
                take = min(3 if rem >= 3 else 2, rem)
                res.append(take)
                rem -= take
            return res

    def _solve_skenario(
        self, timeout_sec, strict_mgmp=True, allow_same_day_multisession=False
    ):
        model = cp_model.CpModel()

        # 1. Deteksi Kolom Fleksibel
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

        # Filter Slot Pembelajaran
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

        # 2. Pecah Tugas Mengajar Menjadi Sesi Mengikuti Logika 3 JP & M05
        sessions = []
        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row[col_mengajar_rombel]).strip()
            guru = str(row[col_mengajar_guru]).strip()
            mapel = str(row[col_mengajar_mapel]).strip()
            total_jp = int(row[col_mengajar_jp])

            raw_blok = blok_map.get(mapel, None)
            durations = self._parse_blok(raw_blok, total_jp, mapel_code=mapel)

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

        # 3. Decision Variables
        S = {}  # Jam mulai sesi
        X = {}  # Jam keterisian slot

        for s in sessions:
            s_id = s["session_id"]
            dur = s["duration"]
            for h, j in slot_tuples:
                X[(s_id, h, j)] = model.NewBoolVar(f"x_{s_id}_{h}_{j}")

            for h in hari_list:
                j_in_h = sorted([sj for (sh, sj) in slot_tuples if sh == h])
                for j in j_in_h:
                    S[(s_id, h, j)] = model.NewBoolVar(f"s_{s_id}_{h}_{j}")

                    # Cek apakah durasi blok cukup dan berurutan
                    block_j = []
                    valid_block = True
                    for k in range(dur):
                        if (j + k) in j_in_h:
                            block_j.append(j + k)
                        else:
                            valid_block = False
                            break

                    if not valid_block:
                        model.Add(S[(s_id, h, j)] == 0)
                    else:
                        # Jika Sesi dimulai di (h, j), kunci jam j s.d. j+dur-1 secara kontinu
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
        # CONSTRAINT 2: Maksimal 1 Sesi Mengajar per Slot per Rombel
        # -------------------------------------------------------------
        for r in rombel_list:
            s_ids_r = [s["session_id"] for s in sessions if s["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_r) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 3: Guru Tidak Boleh Mengajar Bentrok
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
        # CONSTRAINT 4: Distribusi Sesi per Hari
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
                        j_in_h = [sj for (sh, sj) in slot_tuples if sh == h]
                        max_sess = 2 if allow_same_day_multisession else 1
                        model.Add(
                            sum(
                                S[(s["session_id"], h, j)]
                                for s in s_m
                                for j in j_in_h
                            )
                            <= max_sess
                        )

        # -------------------------------------------------------------
        # CONSTRAINT 5: Aturan Mapel M08 (Hanya Boleh Jam Ke 1 s.d. 4)
        # -------------------------------------------------------------
        for s in sessions:
            if str(s["mapel"]).strip().upper() == "M08":
                s_id = s["session_id"]
                for h, j in slot_tuples:
                    if j > 4:
                        model.Add(X[(s_id, h, j)] == 0)

        # -------------------------------------------------------------
        # CONSTRAINT 6: Hari MGMP Guru (Jam > 4 Kosong)
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

        # Jalankan Solver CP-SAT
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
        """Strategi bertahap solver."""

        # Stage 1: Strict MGMP & 1 Sesi Mapel per Hari
        if progress_callback:
            progress_callback(
                "Tahap 1: Memproses jadwal (3 JP Utuh & M05 dipecah 2,1)..."
            )
        t1 = max(20, int(timeout_total * 0.5))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t1,
            strict_mgmp=True,
            allow_same_day_multisession=False,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Optimal (Presisi Sesuai Blok Mapel & MGMP)",
            )

        # Stage 2: Relaksasi MGMP Guru
        if progress_callback:
            progress_callback(
                "Tahap 2: Menyesuaikan aturan MGMP Guru yang padat..."
            )
        t2 = max(20, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t2,
            strict_mgmp=False,
            allow_same_day_multisession=False,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Relaksasi (Sesuai Blok Mapel, MGMP Disesuaikan)",
            )

        # Stage 3: Fleksibilitas Sesi Berbeda pada Hari Sama
        if progress_callback:
            progress_callback(
                "Tahap 3: Mengoptimalkan fleksibilitas slot jam..."
            )
        t3 = max(20, int(timeout_total * 0.2))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t3,
            strict_mgmp=False,
            allow_same_day_multisession=True,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Fleksibel (Semua JP Berhasil Terjadwal)",
            )

        return False, pd.DataFrame(), pd.DataFrame(), "Solver Tidak Menemukan Solusi"

    def generate(self, timeout=120):
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout
        )
        return df_hasil, df_laporan
