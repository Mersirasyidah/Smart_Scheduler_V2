import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df.copy()
        self.rombel_df = rombel_df.copy()
        self.mengajar_df = mengajar_df.copy()
        self.mapel_df = mapel_df.copy()
        self.slot_df = slot_df.copy()

        # Bersihkan spasi berlebih pada seluruh nama kolom
        for df in [
            self.guru_df,
            self.rombel_df,
            self.mengajar_df,
            self.mapel_df,
            self.slot_df,
        ]:
            df.columns = [str(c).strip() for c in df.columns]

    def _find_col(self, df, keywords):
        """Pencarian kolom fleksibel berdasarkan kata kunci."""
        # 1. Cari yang persis / cocok menyeluruh
        for kw in keywords:
            for col in df.columns:
                c_clean = (
                    str(col)
                    .lower()
                    .replace("_", " ")
                    .replace("/", " ")
                    .strip()
                )
                k_clean = kw.lower().replace("_", " ").replace("/", " ").strip()
                if c_clean == k_clean:
                    return col

        # 2. Cari yang mengandung kata kunci (partial match)
        for kw in keywords:
            for col in df.columns:
                c_clean = str(col).lower()
                k_clean = kw.lower()
                if k_clean in c_clean:
                    return col

        return None

    def _parse_blok(self, val_blok, total_jp, allow_split_3jp=False):
        """Aturan pembagian jam baku."""
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
            return [3]  # Utuh 3 JP
        elif total_jp == 5:
            return [2, 2, 1]  # 5 JP -> 2, 2, 1
        elif total_jp == 6:
            return [2, 2, 2]  # 6 JP -> 2, 2, 2
        elif total_jp == 4:
            return [2, 2]  # 4 JP -> 2, 2
        elif total_jp == 2:
            return [2]
        else:
            return [total_jp]

    def _solve_skenario(
        self,
        timeout_sec,
        strict_mgmp=True,
        strict_m08=True,
        allow_same_day_multisession=False,
        allow_split_3jp=False,
    ):
        model = cp_model.CpModel()

        # Deteksi otomatis nama kolom dari Excel Anda
        c_mengajar_rombel = self._find_col(
            self.mengajar_df,
            ["kelas / rombel", "rombel", "kelas", "id_rombel", "id rombel"],
        )
        c_mengajar_guru = self._find_col(
            self.mengajar_df,
            ["nama guru", "guru", "id_guru", "id guru", "pengajar"],
        )
        c_mengajar_mapel = self._find_col(
            self.mengajar_df,
            [
                "mata pelajaran",
                "mapel",
                "id_mapel",
                "id mapel",
                "pelajaran",
                "nama mapel",
            ],
        )
        c_mengajar_jp = self._find_col(
            self.mengajar_df,
            ["beban jp", "beban_jp", "jp", "jumlah jp", "total jp", "jam ke"],
        )

        c_rombel_id = self._find_col(
            self.rombel_df,
            ["kelas / rombel", "rombel", "kelas", "id_rombel", "id rombel"],
        )
        c_guru_id = self._find_col(
            self.guru_df,
            ["nama guru", "guru", "id_guru", "id guru", "nama_guru"],
        )
        c_mapel_id = self._find_col(
            self.mapel_df,
            ["mata pelajaran", "mapel", "id_mapel", "id mapel", "nama mapel"],
        )
        c_mapel_blok = self._find_col(
            self.mapel_df, ["blok", "pembagian", "format_jp"]
        )

        c_slot_hari = self._find_col(self.slot_df, ["hari"])
        c_slot_jam = self._find_col(
            self.slot_df, ["jam ke", "jam_ke", "jam", "ke"]
        )
        c_slot_jenis = self._find_col(self.slot_df, ["jenis", "tipe", "keterangan"])

        # Pengecekan Kritis: Pastikan kolom ditemukan
        if not all(
            [
                c_mengajar_rombel,
                c_mengajar_guru,
                c_mengajar_mapel,
                c_slot_hari,
                c_slot_jam,
            ]
        ):
            print("❌ GAGAL: Ada kolom Excel yang tidak terdeteksi!")
            return False, pd.DataFrame(), pd.DataFrame()

        # Filter Slot Pembelajaran
        if c_slot_jenis and c_slot_jenis in self.slot_df.columns:
            slot_pemb = self.slot_df[
                self.slot_df[c_slot_jenis]
                .astype(str)
                .str.strip()
                .str.upper()
                .str.contains("PEMBELAJARAN|BELAJAR|KBM|KULIAH", regex=True)
            ]
            if slot_pemb.empty:
                slot_pemb = self.slot_df
        else:
            slot_pemb = self.slot_df

        slot_tuples = sorted(
            list(
                set(
                    zip(
                        slot_pemb[c_slot_hari].astype(str).str.strip(),
                        slot_pemb[c_slot_jam].astype(int),
                    )
                )
            )
        )
        hari_list = list(
            dict.fromkeys([sh for (sh, sj) in slot_tuples])
        )  # Unik & urut

        # Mapel Blok Kustom
        blok_map = {}
        if c_mapel_id and c_mapel_blok:
            for _, r_m in self.mapel_df.iterrows():
                m_id = str(r_m[c_mapel_id]).strip()
                blok_map[m_id] = r_m[c_mapel_blok]

        # Daftar Rombel & Guru
        rombel_list = (
            self.rombel_df[c_rombel_id]
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
            if c_rombel_id
            else self.mengajar_df[c_mengajar_rombel]
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        guru_list = (
            self.guru_df[c_guru_id].astype(str).str.strip().unique().tolist()
            if c_guru_id
            else self.mengajar_df[c_mengajar_guru]
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        # Pemisahan Sesi Mengajar Sesuai JP
        sessions = []
        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row[c_mengajar_rombel]).strip()
            guru = str(row[c_mengajar_guru]).strip()
            mapel = str(row[c_mengajar_mapel]).strip()

            # Mengambil beban JP (default 2 jika tak terdeteksi)
            total_jp = 2
            if c_mengajar_jp and pd.notna(row[c_mengajar_jp]):
                try:
                    total_jp = int(row[c_mengajar_jp])
                except:
                    total_jp = 2

            raw_blok = blok_map.get(mapel, None)
            durations = self._parse_blok(
                raw_blok, total_jp, allow_split_3jp=allow_split_3jp
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

        # Decision Variables
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
                        for bj in block_j:
                            model.Add(
                                X[(s_id, h, bj)] == 1
                            ).OnlyEnforceIf(S[(s_id, h, j)])

        # Constraint 1: Setiap Sesi Terpasang
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

        # Constraint 2: Tidak Boleh Tabrakan Rombel
        for r in rombel_list:
            s_ids_r = [s["session_id"] for s in sessions if s["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_r) <= 1)

        # Constraint 3: Guru Tidak Bentrok
        for g in guru_list:
            s_ids_g = [s["session_id"] for s in sessions if s["guru"] == g]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_g) <= 1)

        # Constraint 4: Mapel Sama Maksimal 1x Sehari per Kelas
        if not allow_same_day_multisession:
            for r in rombel_list:
                mapel_in_r = set(
                    s["mapel"] for s in sessions if s["rombel"] == r
                )
                for m in mapel_in_r:
                    s_m = [
                        s
                        for s in sessions
                        if s["rombel"] == r and s["mapel"] == m
                    ]
                    if len(s_m) > 1:
                        for h in hari_list:
                            j_in_h = [
                                sj for (sh, sj) in slot_tuples if sh == h
                            ]
                            model.Add(
                                sum(
                                    S[(s["session_id"], h, j)]
                                    for s in s_m
                                    for j in j_in_h
                                )
                                <= 1
                            )

        # Constraint 5: Batasan Mapel Pancasila / M08 (Jam 1 s.d 4)
        if strict_m08:
            for s in sessions:
                if "pancasila" in str(s["mapel"]).lower() or str(
                    s["mapel"]
                ).strip().upper() == "M08":
                    s_id = s["session_id"]
                    for h, j in slot_tuples:
                        if j > 4:
                            model.Add(X[(s_id, h, j)] == 0)

        # Constraint 6: MGMP Guru (Setelah Jam 4)
        c_guru_mgmp = (
            self._find_col(self.guru_df, ["mgmp", "hari_mgmp", "hari mgmp"])
            if self.guru_df is not None
            else None
        )
        if strict_mgmp and c_guru_mgmp and c_guru_id:
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

        # Solver Output
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
                                "Jam Ke": j,
                                "Kelas / Rombel": s["rombel"],
                                "Nama Guru": s["guru"],
                                "Mata Pelajaran": s["mapel"],
                            }
                        )

            df_res = pd.DataFrame(results)
            if not df_res.empty:
                df_res = df_res.sort_values(
                    by=["Kelas / Rombel", "Hari", "Jam Ke"]
                ).reset_index(drop=True)

            df_laporan = (
                df_res.groupby("Nama Guru", as_index=False)
                .size()
                .rename(columns={"size": "Total_JP_Terjadwal"})
            )
            return True, df_res, df_laporan
        else:
            return False, pd.DataFrame(), pd.DataFrame()

    def solve_with_fallback(self, timeout_total=180, progress_callback=None):
        if progress_callback:
            progress_callback(
                "Membaca data Excel & Menjalankan Solver Utama..."
            )

        # Iterasi 1: Aturan Baku Murni
        t1 = max(30, int(timeout_total * 0.4))
        success, df_res, df_lap = self._solve_skenario(
            t1,
            strict_mgmp=True,
            strict_m08=True,
            allow_same_day_multisession=False,
            allow_split_3jp=False,
        )
        if success:
            return True, df_res, df_lap, "Selesai (Aturan Baku & MGMP Strict)"

        # Iterasi 2: Relaksasi MGMP
        if progress_callback:
            progress_callback("Skenario 2: Melonggarkan jadwal MGMP Guru...")
        t2 = max(25, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            t2,
            strict_mgmp=False,
            strict_m08=True,
            allow_same_day_multisession=False,
            allow_split_3jp=False,
        )
        if success:
            return True, df_res, df_lap, "Selesai (Relaksasi Jam MGMP Guru)"

        # Iterasi 3: Relaksasi M08 & Multi Sesi
        if progress_callback:
            progress_callback("Skenario 3: Melonggarkan batasan jam Mapel...")
        t3 = max(20, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            t3,
            strict_mgmp=False,
            strict_m08=False,
            allow_same_day_multisession=True,
            allow_split_3jp=True,
        )
        if success:
            return True, df_res, df_lap, "Selesai (Penyusunan Fleksibel)"

        return (
            False,
            pd.DataFrame(),
            pd.DataFrame(),
            "Gagal membaca/menyusun jadwal.",
        )

    def generate(self, timeout=120):
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout
        )
        return df_hasil, df_laporan
