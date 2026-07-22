import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df.copy()
        self.rombel_df = rombel_df.copy()
        self.mengajar_df = mengajar_df.copy()
        self.mapel_df = mapel_df.copy()
        self.slot_df = slot_df.copy()

        # Pembersihan nama kolom agar fleksibel terhadap spasi / huruf besar-kecil
        for df in [
            self.guru_df,
            self.rombel_df,
            self.mengajar_df,
            self.mapel_df,
            self.slot_df,
        ]:
            df.columns = [str(c).strip() for c in df.columns]

    def _get_col(self, df, possible_names):
        """Pencarian nama kolom secara dinamis."""
        for name in possible_names:
            for col in df.columns:
                c_clean = str(col).strip().lower().replace("_", " ")
                n_clean = name.lower().replace("_", " ")
                if c_clean == n_clean:
                    return col
        return df.columns[0]

    def _parse_blok(self, val_blok, total_jp, mapel_code):
        """
        Aturan Pembagian Blok Jam Baku:
        1. Membaca spesifik dari Excel jika kolom Blok pada sheet Mapel terisi manual.
        2. Jika kosong, menerapkan aturan baku:
           - 3 JP -> [3]       (Utuh 3 jam, tidak dipisah)
           - 5 JP -> [2, 2, 1] (Dipecah 2, 2, 1)
           - 6 JP -> [2, 2, 2] (Dipecah 2, 2, 2)
           - 4 JP -> [2, 2]
           - 2 JP -> [2]
        """
        # 1. Prioritas Utama: Kustomisasi dari kolom 'Blok' sheet Mapel
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

        # 2. Aturan Baku Pembagian Jam
        if total_jp == 3:
            return [3]  # Utuh 3 JP sekaligus
        elif total_jp == 5:
            return [2, 2, 1]  # Dipecah 2, 2, 1
        elif total_jp == 6:
            return [2, 2, 2]  # Dipecah 2, 2, 2
        elif total_jp == 4:
            return [2, 2]  # Dipecah 2, 2
        elif total_jp == 2:
            return [2]  # Utuh 2 JP
        else:
            return [total_jp]

    def _solve_skenario(
        self,
        timeout_sec,
        strict_mgmp=True,
        strict_m08=True,
        allow_same_day_multisession=False,
    ):
        model = cp_model.CpModel()

        # 1. Deteksi Kolom Dataset
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

        # 2. Pemisahan Sesi Mengajar Berdasarkan Aturan Pembagian Jam
        sessions = []
        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row[col_mengajar_rombel]).strip()
            guru = str(row[col_mengajar_guru]).strip()
            mapel = str(row[col_mengajar_mapel]).strip()
            total_jp = int(row[col_mengajar_jp])

            raw_blok = blok_map.get(mapel, None)
            durations = self._parse_blok(
                raw_blok, total_jp, mapel_code=mapel
            )

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

        # CONSTRAINT 1: Setiap Sesi Ditempatkan Tepat 1 Kali Secara Utuh
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

        # CONSTRAINT 2: Maksimal 1 Sesi per Slot Jam per Rombel (Mencegah Tabrakan Kelas)
        for r in rombel_list:
            s_ids_r = [s["session_id"] for s in sessions if s["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(s_id, h, j)] for s_id in s_ids_r) <= 1)

        # CONSTRAINT 3: Guru Tidak Boleh Mengajar di 2 Kelas Sekaligus
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

        # CONSTRAINT 4: Batasan Pertemuan Mapel Sama di Hari yang Sama
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

        # CONSTRAINT 5: Aturan Khusus Mapel M08 (Jam 1 s.d. 4)
        if strict_m08:
            for s in sessions:
                if str(s["mapel"]).strip().upper() == "M08":
                    s_id = s["session_id"]
                    for h, j in slot_tuples:
                        if j > 4:
                            model.Add(X[(s_id, h, j)] == 0)

        # CONSTRAINT 6: MGMP Guru (Dilarang Mengajar di Atas Jam ke-4 Saat MGMP)
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

        # Eksekusi Solver CP-SAT
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
        """
        Pencarian Solusi Bertahap (Mencegah Gagal/Infeasible):
        - Skenario 1: Aturan Baku (3 JP Utuh, 5 JP [2,2,1], 6 JP [2,2,2] + MGMP Ketat)
        - Skenario 2: Melonggarkan Batasan Hari MGMP Guru
        - Skenario 3: Melonggarkan Batasan Mapel M08 (Boleh di Atas Jam ke-4)
        - Skenario 4: Fleksibilitas Tambahan Sesi
        """

        # Skenario 1: Utama (Aturan Baku & MGMP Strict)
        if progress_callback:
            progress_callback(
                "Mencari solusi utama (3 JP Utuh, 5 JP [2,2,1], 6 JP [2,2,2] & MGMP)..."
            )
        t1 = max(30, int(timeout_total * 0.4))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t1,
            strict_mgmp=True,
            strict_m08=True,
            allow_same_day_multisession=False,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Berhasil Ditemukan (Sesuai Aturan Jam & MGMP)",
            )

        # Skenario 2: Lepas Batasan MGMP Guru
        if progress_callback:
            progress_callback(
                "Skenario 1 tidak cukup space. Melonggarkan batasan MGMP Guru..."
            )
        t2 = max(25, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t2,
            strict_mgmp=False,
            strict_m08=True,
            allow_same_day_multisession=False,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Berhasil Ditemukan (Relaksasi Jam MGMP Guru)",
            )

        # Skenario 3: Lepas Pembatasan M08
        if progress_callback:
            progress_callback(
                "Melonggarkan batasan jam mengajar Mapel M08..."
            )
        t3 = max(20, int(timeout_total * 0.2))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t3,
            strict_mgmp=False,
            strict_m08=False,
            allow_same_day_multisession=False,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Berhasil Ditemukan (Relaksasi MGMP & Mapel M08)",
            )

        # Skenario 4: Izinkan Multi Sesi Fleksibel
        if progress_callback:
            progress_callback("Mencoba opsi penyusunan fleksibel akhir...")
        t4 = max(15, int(timeout_total * 0.1))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t4,
            strict_mgmp=False,
            strict_m08=False,
            allow_same_day_multisession=True,
        )
        if success:
            return (
                True,
                df_res,
                df_lap,
                "Solusi Ditemukan (Relaksasi Sesi Fleksibel)",
            )

        return (
            False,
            pd.DataFrame(),
            pd.DataFrame(),
            "Solver Gagal: Terjadi bentrok slot/beban JP yang secara matematis tidak muat diselesaikan.",
        )

    def generate(self, timeout=120):
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout
        )
        return df_hasil, df_laporan
