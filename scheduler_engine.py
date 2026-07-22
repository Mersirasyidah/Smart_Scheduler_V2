import pandas as pd
from ortools.sat.python import cp_model


class Scheduler:

    def __init__(self, guru_df, rombel_df, mengajar_df, mapel_df, slot_df):
        self.guru_df = guru_df
        self.rombel_df = rombel_df
        self.mengajar_df = mengajar_df
        self.mapel_df = mapel_df
        self.slot_df = slot_df

        # Clean dataframe column names
        for df in [
            self.guru_df,
            self.rombel_df,
            self.mengajar_df,
            self.mapel_df,
            self.slot_df,
        ]:
            df.columns = [str(c).strip() for c in df.columns]

    def _solve_skenario(self, timeout_sec, strict_mgmp=True):
        model = cp_model.CpModel()

        # Extract List Data
        rombel_list = self.rombel_df["ID_Rombel"].astype(str).str.strip().tolist()
        
        # Ambil slot berjenis 'PEMBELAJARAN' saja
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

        hari_list = slot_pemb["Hari"].astype(str).str.strip().unique().tolist()
        
        # Buat daftar unik (Hari, Jam_Ke)
        slot_tuples = []
        for _, row in slot_pemb.iterrows():
            slot_tuples.append((str(row["Hari"]).strip(), int(row["Jam_Ke"])))
        slot_tuples = list(set(slot_tuples))

        # Variabel Keputusan X[tugas_idx, hari, jam]
        X = {}
        tugas_info = []

        for idx, row in self.mengajar_df.iterrows():
            rombel = str(row["ID_Rombel"]).strip()
            guru = str(row["ID_Guru"]).strip()
            mapel = str(row["ID_Mapel"]).strip()
            jp = int(row["Beban_JP"])

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
        # CONSTRAINT 1: Setiap Tugas Mengajar Harus Terpenuhi Beban JP-nya
        # -------------------------------------------------------------
        for t in tugas_info:
            model.Add(
                sum(X[(t["idx"], h, j)] for h, j in slot_tuples) == t["jp"]
            )

        # -------------------------------------------------------------
        # CONSTRAINT 2: Dalam 1 Rombel & 1 Slot Waktu, Max 1 Mapel
        # -------------------------------------------------------------
        for r in rombel_list:
            tugas_rombel = [t["idx"] for t in tugas_info if t["rombel"] == r]
            for h, j in slot_tuples:
                model.Add(sum(X[(idx, h, j)] for idx in tugas_rombel) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 3: Seorang Guru Tidak Boleh Mengajar di 2 Kelas Bersamaan
        # -------------------------------------------------------------
        guru_list = self.guru_df["ID_Guru"].astype(str).str.strip().tolist()
        for g in guru_list:
            tugas_guru = [t["idx"] for t in tugas_info if t["guru"] == g]
            for h, j in slot_tuples:
                model.Add(sum(X[(idx, h, j)] for idx in tugas_guru) <= 1)

        # -------------------------------------------------------------
        # CONSTRAINT 4 (DIPERKETAT): MAX 2 JP PER HARI UNTUK MAPEL MANAPUN
        # -------------------------------------------------------------
        # Mencegah mapel seperti M06, M10, dll. diajarkan 3 JP sekaligus dalam sehari
        for r in rombel_list:
            # Kelompokkan tugas berdasarkan mapel di rombel tersebut
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
                    slots_in_h = [
                        (sh, sj) for (sh, sj) in slot_tuples if sh == h
                    ]
                    # Maksimal 2 JP per hari untuk mapel yang sama di kelas yang sama
                    model.Add(
                        sum(
                            X[(idx, h, j)]
                            for idx in tugas_m
                            for (sh, sj) in slots_in_h
                            if sh == h and (idx, h, sj) in X
                        )
                        <= 2
                    )

        # -------------------------------------------------------------
        # CONSTRAINT 5 (ATURAN KHUSUS M08): Wajib di Jam Ke 1 - 4
        # -------------------------------------------------------------
        for t in tugas_info:
            if t["mapel"].upper() == "M08":
                for h, j in slot_tuples:
                    if j > 4:
                        # M08 tidak boleh dijadwalkan di jam ke-5 ke atas
                        model.Add(X[(t["idx"], h, j)] == 0)

        # -------------------------------------------------------------
        # CONSTRAINT 6: Handling MGMP / Hari Khusus Guru
        # -------------------------------------------------------------
        if strict_mgmp and "Hari_MGMP" in self.guru_df.columns:
            for _, row in self.guru_df.iterrows():
                g_id = str(row["ID_Guru"]).strip()
                mgmp_day = (
                    str(row["Hari_MGMP"]).strip()
                    if pd.notna(row.get("Hari_MGMP"))
                    else ""
                )

                if mgmp_day and mgmp_day.lower() != "nan":
                    tugas_g = [
                        t["idx"] for t in tugas_info if t["guru"] == g_id
                    ]
                    # Guru tidak boleh mengajar di hari MGMP pada jam > 4 (misal acara MGMP siang)
                    for h, j in slot_tuples:
                        if h.lower() == mgmp_day.lower() and j > 4:
                            for idx in tugas_g:
                                model.Add(X[(idx, h, j)] == 0)

        # -------------------------------------------------------------
        # SOLVER EXECUTION
        # -------------------------------------------------------------
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

            # Reorientasi Laporan Guru
            df_laporan = (
                df_res.groupby("ID_Guru")
                .agg(Total_JP=("Jam_Ke", "count"))
                .reset_index()
            )

            return True, df_res, df_laporan
        else:
            return False, pd.DataFrame(), pd.DataFrame()

    def solve_with_fallback(self, timeout_total=180, progress_callback=None):
        """Strategi eksekusi bertahap (strict -> relaxed mgmp)."""

        # Tahap 1: Skenario Ketat (Termasuk Aturan MGMP Strict)
        if progress_callback:
            progress_callback(
                "Mencari jadwal optimal (Batas max 2 JP/hari & M08 jam 1-4)..."
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
                "Skenario Optimal (MGMP Strict & M08 Jam 1-4)",
            )

        # Tahap 2: Skenario Relaksasi MGMP jika Skenario 1 tidak dapat solusi
        if progress_callback:
            progress_callback("Mencoba relaksasi batas MGMP guru...")

        t_rem = max(30, int(timeout_total * 0.3))
        success, df_res, df_lap = self._solve_skenario(
            timeout_sec=t_rem, strict_mgmp=False
        )

        if success:
            return (
                True,
                df_res,
                df_lap,
                "Skenario Relaksasi (MGMP Disesuaikan, M08 Tetap Jam 1-4)",
            )

        return False, pd.DataFrame(), pd.DataFrame(), "Solver Tidak Menemukan Solusi"

    def generate(self, timeout=120):
        """Alias kompatibilitas versi lama."""
        success, df_hasil, df_laporan, _ = self.solve_with_fallback(
            timeout_total=timeout
        )
        return df_hasil, df_laporan
