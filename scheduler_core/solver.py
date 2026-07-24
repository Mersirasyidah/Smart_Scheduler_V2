import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df.copy() if guru_df is not None else pd.DataFrame()
        self.rombel_df = (
            rombel_df.copy() if rombel_df is not None else pd.DataFrame()
        )
        self.mengajar_df = (
            mengajar_df.copy() if mengajar_df is not None else pd.DataFrame()
        )
        self.mapel_df = (
            mapel_df.copy() if mapel_df is not None else pd.DataFrame()
        )
        self.slot_df = slot_df.copy() if slot_df is not None else pd.DataFrame()

        # Normalisasi nama kolom (hapus spasi depan/belakang)
        for df in [
            self.guru_df,
            self.rombel_df,
            self.mengajar_df,
            self.mapel_df,
            self.slot_df,
        ]:
            if not df.empty:
                df.columns = [str(c).strip() for c in df.columns]

    def _get_safe_col(self, df, keywords):
        """Pencarian nama kolom dinamis agar aman dari KeyError."""
        if df.empty:
            return None

        for kw in keywords:
            for col in df.columns:
                c_clean = (
                    str(col)
                    .lower()
                    .replace("_", "")
                    .replace(" ", "")
                    .replace("/", "")
                )
                k_clean = (
                    kw.lower()
                    .replace("_", "")
                    .replace(" ", "")
                    .replace("/", "")
                )
                if c_clean == k_clean:
                    return col

        for kw in keywords:
            for col in df.columns:
                if kw.lower() in str(col).lower():
                    return col

        return df.columns[0] if len(df.columns) > 0 else None

    def _parse_blok(self, val_blok, total_jp, allow_split_3jp=False):
        """Membagi JP menjadi durasi blok presisi."""
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
            if sum(durations) == total_jp and len(durations) > 0:
                return durations

        if allow_split_3jp and total_jp == 3:
            return [2, 1]

        if total_jp == 3:
            return [3]
        elif total_jp == 5:
            return [2, 2, 1]
        elif total_jp == 6:
            return [2, 2, 2]
        elif total_jp == 4:
            return [2, 2]
        elif total_jp == 2:
            return [2]
        else:
            return [total_jp]

    def _solve_skenario(
        self,
        timeout_sec,
        strict_mgmp=True,
        strict_m08=True,
        strict_pagi=True,
        max_jp_guru_per_hari=6,
        max_mapel_per_hari=5,
        num_workers=4,
        log_progress=False,
    ):
        model = cp_model.CpModel()

        # Deteksi Kolom Mengajar
        c_mengajar_rombel = self._get_safe_col(
            self.mengajar_df,
            ["id_rombel", "rombel", "kelas", "id kelas", "kelas / rombel"],
        )
        c_mengajar_guru = self._get_safe_col(
            self.mengajar_df,
            ["id_guru", "guru", "nama guru", "id guru", "pengajar"],
        )
        c_mengajar_mapel = self._get_safe_col(
            self.mengajar_df,
            ["id_mapel", "mapel", "mata pelajaran", "id mapel", "nama mapel"],
        )
        c_mengajar_jp = self._get_safe_col(
            self.mengajar_df,
            ["beban_jp", "beban jp", "jp", "jumlah jp", "total jp"],
        )

        # Deteksi Kolom Slot
        c_slot_hari = self._get_safe_col(
            self.slot_df, ["hari", "day", "hari kbm"]
        )
        c_slot_jam = self._get_safe_col(
            self.slot_df, ["jam_ke", "jam ke", "jam", "ke", "jamke"]
        )
        c_slot_jenis = self._get_safe_col(
            self.slot_df, ["jenis", "tipe", "keterangan", "status"]
        )

        if self.mengajar_df.empty or self.slot_df.empty:
            return False, pd.DataFrame(), pd.DataFrame()

        # Filter Slot Pembelajaran Utamakan KBM
        if c_slot_jenis and c_slot_jenis in self.slot_df.columns:
            mask = (
                self.slot_df[c_slot_jenis]
                .astype(str)
                .str.strip()
                .str.upper()
                .str.contains("PEMBELAJARAN|BELAJAR|KBM|UTAMA", regex=True)
            )
            slot_pemb = self.slot_df[mask]
            if slot_pemb.empty:
                slot_pemb = self.slot_df
        else:
            slot_pemb = self.slot_df

        slot_tuples = []
        for _, r in slot_pemb.iterrows():
            try:
                h_val = str(r[c_slot_hari]).strip()
                j_val = int(r[c_slot_jam])
                slot_tuples.append((h_val, j_val))
            except (ValueError, KeyError):
                continue

        slot_tuples = sorted(list(set(slot_tuples)))
        if not slot_tuples:
            return False, pd.DataFrame(), pd.DataFrame()

        hari_list = list(dict.fromkeys([sh for (sh, sj) in slot_tuples]))

        # Deteksi Mapel & Format Blok
        c_mapel_id = self._get_safe_col(
            self.mapel_df,
            ["id_mapel", "mapel", "mata pelajaran", "id mapel", "nama mapel"],
        )
        c_mapel_blok = self._get_safe_col(
            self.mapel_df, ["blok", "pembagian", "format_jp"]
        )

        blok_map = {}
        if (
            not self.mapel_df.empty
            and c_mapel_id
            and c_mapel_blok
            and c_mapel_blok in self.mapel_df.columns
        ):
            for _, r_m in self.mapel_df.iterrows():
                m_id = str(r_m[c_mapel_id]).strip()
                blok_map[m_id] = r_m[c_mapel_blok]

        # Pembentukan Sesi Mengajar
        sessions = []
        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row[c_mengajar_rombel]).strip()
            guru = str(row[c_mengajar_guru]).strip()
            mapel = str(row[c_mengajar_mapel]).strip()

            try:
                total_jp = int(row[c_mengajar_jp])
            except (ValueError, TypeError):
                total_jp = 2

            raw_blok = blok_map.get(mapel, None)
            durations = self._parse_blok(
                raw_blok, total_jp, allow_split_3jp=False
            )

            for s_idx, dur in enumerate(durations):
                sessions.append(
                    {
                        "session_id": f"{idx}_s{s_idx}",
                        "rombel": rombel,
                        "guru": guru,
                        "mapel": mapel,
                        "duration": dur,
                    }
                )

        if not sessions:
            return False, pd.DataFrame(), pd.DataFrame()

        rombel_list = list(set(s["rombel"] for s in sessions))
        guru_list = list(set(s["guru"] for s in sessions))

        # Variabel Keputusan (Decision Variables)
        S = {}
        X = {}

        for s in sessions:
            s_id = s["session_id"]
            dur = s["duration"]
            for h, j in slot_tuples:
                X[(s_id, h, j)] = model.NewBoolVar(f"x_{s_id}_{h}_{j}")

            for h in hari_list:
                j_in_h = sorted([sj for (sh, sj) in slot_tuples if sh == h])
                for j in j_in_h:
                    S[(s_id, h, j)] = model.NewBoolVar(f"s_{s_id}_{h}_{j}")

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
                        # Jika S[(s_id, h, j)] aktif, maka X untuk slot blok harus aktif
                        for bj in block_j:
                            model.Add(
                                X[(s_id, h, bj)] == 1
                            ).OnlyEnforceIf(S[(s_id, h, j)])

            # KUNCI PERBAIKAN BUG #1: Hubungkan total X dengan total S x Duration
            # Mencegah X terisi tanpa adanya S awal
            for h in hari_list:
                j_in_h = [sj for (sh, sj) in slot_tuples if sh == h]
                model.Add(
                    sum(X[(s_id, h, j)] for j in j_in_h)
                    == sum(S[(s_id, h, j)] for j in j_in_h) * dur
                )

        # ==================== ATURAN MUTLAK (HARD CONSTRAINTS) ====================

        # 1. Pasang Setiap Sesi Tepat 1 Kali
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

        # 2. Rombel Tidak Bentrok
        for r in rombel_list:
            s_ids_r = [s["session_id"] for s in sessions if s["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_r) <= 1)

        # 3. Guru Tidak Bentrok
        for g in guru_list:
            s_ids_g = [s["session_id"] for s in sessions if s["guru"] == g]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_g) <= 1)

        # 4. Mapel Sama Maksimal 1x Sehari per Rombel
        for r in rombel_list:
            mapel_in_r = set(s["mapel"] for s in sessions if s["rombel"] == r)
            for m in mapel_in_r:
                s_m = [
                    s for s in sessions if s["rombel"] == r and s["mapel"] == m
                ]
                if len(s_m) > 1:
                    for h in hari_list:
                        j_in_h = [sj for (sh, sj) in slot_tuples if sh == h]
                        model.Add(
                            sum(
                                S[(s["session_id"], h, j)]
                                for s in s_m
                                for j in j_in_h
                            )
                            <= 1
                        )

        # 5. MAKSIMAL SESI MAPEL PER HARI PER ROMBEL (Dioptimalkan agar Solver Cepat)
        if max_mapel_per_hari is not None and max_mapel_per_hari > 0:
            for r in rombel_list:
                s_ids_r = [s["session_id"] for s in sessions if s["rombel"] == r]
                for h in hari_list:
                    j_in_h = [sj for (sh, sj) in slot_tuples if sh == h]
                    model.Add(
                        sum(S[(s_id, h, j)] for s_id in s_ids_r for j in j_in_h)
                        <= max_mapel_per_hari
                    )

        # 6. BATASAN MAKSIMAL JP GURU PER HARI (Pemerataan Beban)
        if max_jp_guru_per_hari is not None and max_jp_guru_per_hari > 0:
            for g in guru_list:
                s_ids_g = [s["session_id"] for s in sessions if s["guru"] == g]
                for h in hari_list:
                    j_in_h = [sj for (sh, sj) in slot_tuples if sh == h]
                    model.Add(
                        sum(X[(s_id, h, j)] for s_id in s_ids_g for j in j_in_h)
                        <= max_jp_guru_per_hari
                    )

        # 7. BATASAN JAM PAGI (Pancasila / M08 & Olahraga PJOK)
        if strict_m08 or strict_pagi:
            for s in sessions:
                m_name = str(s["mapel"]).lower()
                s_id = s["session_id"]

                # Pancasila / M08 -> Jam 1-4
                if "pancasila" in m_name or "m08" in m_name.upper():
                    for h, j in slot_tuples:
                        if j > 4:
                            model.Add(X[(s_id, h, j)] == 0)

                # Olahraga / PJOK -> Jam 1-3
                if "olahraga" in m_name or "pjok" in m_name:
                    for h, j in slot_tuples:
                        if j > 3:
                            model.Add(X[(s_id, h, j)] == 0)

        # 8. HARI MGMP GURU
        c_guru_id = self._get_safe_col(
            self.guru_df, ["id_guru", "guru", "nama guru", "id guru"]
        )
        c_guru_mgmp = self._get_safe_col(
            self.guru_df, ["mgmp", "hari_mgmp", "hari mgmp"]
        )

        if (
            strict_mgmp
            and not self.guru_df.empty
            and c_guru_id
            and c_guru_mgmp
            and c_guru_mgmp in self.guru_df.columns
        ):
            for _, row in self.guru_df.iterrows():
                g_id = str(row[c_guru_id]).strip()
                mgmp_day = (
                    str(row[c_guru_mgmp]).strip()
                    if pd.notna(row.get(c_guru_mgmp))
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

        # ==================== ATURAN KERAPIAN (SOFT CONSTRAINTS) ====================
        penalty_terms = []

        # Pinalti Jam Akhir (Memadatkan Pelajaran dari Jam Pertama)
        for s in sessions:
            s_id = s["session_id"]
            m_name = str(s["mapel"]).lower()
            is_heavy = any(
                k in m_name
                for k in ["matematika", "mtk", "ipa", "fisika", "inggris"]
            )

            for h, j in slot_tuples:
                weight = (j * 5) if is_heavy else (j * 2)
                penalty_terms.append(X[(s_id, h, j)] * weight)

        model.Minimize(sum(penalty_terms))

        # ==================== EKSEKUSI CP-SAT SOLVER ====================
        solver = cp_model.CpSolver()

        solver.parameters.max_time_in_seconds = float(timeout_sec)
        solver.parameters.num_search_workers = int(num_workers)
        solver.parameters.log_search_progress = bool(log_progress)

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

    def solve_with_fallback(
        self,
        timeout_total=180,
        num_workers=4,
        log_progress=False,
        progress_callback=None,
    ):
        if progress_callback:
            progress_callback(
                "Menyusun Jadwal Sesuai Seluruh Peraturan Baku Sekolah..."
            )

        # Skenario 1: Full Strict Rules (Ideal)
        t1 = max(40, int(timeout_total * 0.5))
        success, df_res, df_lap = self._solve_skenario(
            t1,
            strict_mgmp=True,
            strict_m08=True,
            strict_pagi=True,
            max_jp_guru_per_hari=6,
            max_mapel_per_hari=5,
            num_workers=num_workers,
            log_progress=log_progress,
        )
        if success:
            return True, df_res, df_lap, "Selesai (Memenuhi 100% Peraturan Baku)"

        # Skenario 2: Penyesuaian MGMP Guru
        if progress_callback:
            progress_callback(
                "Mengoptimalkan Jadwal (Penyesuaian MGMP Guru)..."
            )
        t2 = max(30, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            t2,
            strict_mgmp=False,
            strict_m08=True,
            strict_pagi=True,
            max_jp_guru_per_hari=7,
            max_mapel_per_hari=5,
            num_workers=num_workers,
            log_progress=log_progress,
        )
        if success:
            return True, df_res, df_lap, "Selesai (Relaksasi Jam MGMP Guru)"

        # Skenario 3: Mode Fleksibel
        if progress_callback:
            progress_callback("Penyusunan Mode Fleksibel...")
        t3 = max(20, int(timeout_total * 0.2))
        success, df_res, df_lap = self._solve_skenario(
            t3,
            strict_mgmp=False,
            strict_m08=False,
            strict_pagi=False,
            max_jp_guru_per_hari=8,
            max_mapel_per_hari=5,
            num_workers=num_workers,
            log_progress=log_progress,
        )
        if success:
            return True, df_res, df_lap, "Selesai (Mode Fleksibel)"

        return (
            False,
            pd.DataFrame(),
            pd.DataFrame(),
            "Gagal menyusun jadwal. Mohon periksa jumlah slot jam KBM atau beban JP guru.",
        )

    def generate(self, timeout=120, num_workers=4, log_progress=False):
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout,
            num_workers=num_workers,
            log_progress=log_progress,
        )
        return df_hasil, df_laporan
