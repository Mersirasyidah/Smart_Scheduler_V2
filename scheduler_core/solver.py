import pandas as pd
from ortools.sat.python import cp_model

class SchedulerSolver:
    def __init__(self, scheduler_or_data, days=None, max_hours=8):
        if hasattr(scheduler_or_data, 'guru'):
            self.guru_df = scheduler_or_data.guru
            self.rombel_df = scheduler_or_data.rombel
            self.mengajar_df = scheduler_or_data.mengajar
            self.mapel_df = scheduler_or_data.mapel
            self.slot_df = scheduler_or_data.slot
        elif isinstance(scheduler_or_data, dict):
            self.guru_df = scheduler_or_data.get("guru")
            self.rombel_df = scheduler_or_data.get("rombel")
            self.mengajar_df = scheduler_or_data.get("mengajar")
            self.mapel_df = scheduler_or_data.get("mapel")
            self.slot_df = scheduler_or_data.get("slot")

        self.days = days if days is not None and len(days) > 0 else ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
        self.max_hours = max_hours if max_hours > 0 else 8
        self.assignments = []
        self.results_df = pd.DataFrame()

    def _get_first_name(self, full_name):
        """Mengambil nama awal guru saja agar tampilan ringkas"""
        if pd.isna(full_name) or not str(full_name).strip():
            return ""
        # Menghapus gelar umum jika ada dan mengambil kata pertama
        clean_name = str(full_name).replace("S.Pd", "").replace("M.Pd", "").replace("S.Ag", "").strip()
        parts = clean_name.split()
        return parts[0] if parts else str(full_name)

    def parse_slot_pattern(self, slot_val, total_jp):
        """Memecah pola slot (misal '2,2,1') menjadi durasi [2, 2, 1]"""
        if pd.isna(slot_val) or not str(slot_val).strip():
            blocks = []
            sisa = total_jp
            while sisa > 0:
                take = 2 if sisa >= 2 else 1
                blocks.append(take)
                sisa -= take
            return blocks

        raw_str = str(slot_val).replace("+", ",").replace(" ", ",").replace("-", ",")
        parts = [p.strip() for p in raw_str.split(",") if p.strip().isdigit()]
        blocks = [int(p) for p in parts if int(p) > 0]

        if sum(blocks) != total_jp:
            blocks = []
            sisa = total_jp
            while sisa > 0:
                take = 2 if sisa >= 2 else 1
                blocks.append(take)
                sisa -= take

        return blocks if len(blocks) > 0 else [total_jp]

    def solve(self, time_limit=120):
        model = cp_model.CpModel()
        
        # Mapping Kolom
        col_guru_id = next((c for c in self.mengajar_df.columns if 'guru' in c.lower()), 'ID_Guru')
        col_rombel = next((c for c in self.mengajar_df.columns if 'rombel' in c.lower() or 'kelas' in c.lower()), 'ID_Rombel')
        col_mapel = next((c for c in self.mengajar_df.columns if 'mapel' in c.lower()), 'ID_Mapel')
        col_jp = next((c for c in self.mengajar_df.columns if 'jp' in c.lower() or 'jam' in c.lower()), 'Beban_JP')
        col_slot = next((c for c in self.mengajar_df.columns if 'slot' in c.lower() or 'pembagian' in c.lower()), 'Slot')

        # Kamus Data Guru (Nama Awal, Status GTT/PNS, Hari MGMP)
        guru_info = {}
        if self.guru_df is not None and not self.guru_df.empty:
            g_id_col = self.guru_df.columns[0]
            g_nama_col = next((c for c in self.guru_df.columns if 'nama' in c.lower()), g_id_col)
            g_status_col = next((c for c in self.guru_df.columns if 'status' in c.lower() or 'gtt' in c.lower()), None)
            g_mgmp_col = next((c for c in self.guru_df.columns if 'mgmp' in c.lower() or 'hari_libur' in c.lower()), None)

            for _, g_row in self.guru_df.iterrows():
                gid = str(g_row[g_id_col]).strip()
                fn = self._get_first_name(g_row[g_nama_col])
                status = str(g_row[g_status_col]).upper() if g_status_col and pd.notna(g_row[g_status_col]) else "NON-GTT"
                is_gtt = "GTT" in status
                mgmp_day = str(g_row[g_mgmp_col]).strip().title() if g_mgmp_col and pd.notna(g_row[g_mgmp_col]) else None

                guru_info[gid] = {
                    'display_name': f"{gid} - {fn}" if fn else gid,
                    'is_gtt': is_gtt,
                    'mgmp_day': mgmp_day
                }

        # 1. Breakout Tasks
        tasks = []
        task_id = 0
        for _, row in self.mengajar_df.iterrows():
            gid = str(row[col_guru_id]).strip()
            rombel = str(row[col_rombel]).strip()
            mapel = str(row[col_mapel]).strip()
            
            try:
                total_jp = int(row[col_jp])
            except (ValueError, TypeError):
                continue
            
            slot_val = row.get(col_slot, None)
            durations = self.parse_slot_pattern(slot_val, total_jp)

            for dur in durations:
                tasks.append({
                    'id': task_id,
                    'guru_id': gid,
                    'rombel': rombel,
                    'mapel': mapel,
                    'duration': dur
                })
                task_id += 1

        if not tasks:
            return False

        num_days = len(self.days)
        X = {}

        # 2. Decision Variables & Constraint MGMP / Senin Jam ke-1
        for t in tasks:
            t_id = t['id']
            dur = t['duration']
            gid = t['guru_id']
            g_meta = guru_info.get(gid, {'is_gtt': False, 'mgmp_day': None})

            for d_idx, day_name in enumerate(self.days):
                for h in range(1, self.max_hours - dur + 2):
                    
                    # ATURAN HARI SENIN: Pelajaran baru mulai Jam ke-2
                    if day_name == 'Senin' and h == 1:
                        continue # Jam 1 Senin dikunci untuk Upacara

                    # ATURAN MGMP
                    if g_meta['mgmp_day'] and g_meta['mgmp_day'].lower() == day_name.lower():
                        if g_meta['is_gtt']:
                            # GTT LIBUR TOTAL DI HARI MGMP
                            continue
                        else:
                            # NON-GTT MAKSIMAL HANYA SAMPAI JAM KE-3
                            if (h + dur - 1) > 3:
                                continue

                    X[(t_id, d_idx, h)] = model.NewBoolVar(f'x_{t_id}_{d_idx}_{h}')

        # 3. Constraint: Setiap task harus dipasang TEPAT 1 KALI
        for t in tasks:
            t_id = t['id']
            dur = t['duration']
            possible_starts = [
                X[(t_id, d, h)] 
                for d in range(num_days) 
                for h in range(1, self.max_hours - dur + 2)
                if (t_id, d, h) in X
            ]
            if possible_starts:
                model.AddExactlyOne(possible_starts)

        # 4. Constraint: Tidak Boleh Bentrok Rombel
        rombel_list = sorted(list(set(t['rombel'] for t in tasks)))
        for rombel_name in rombel_list:
            rombel_tasks = [t for t in tasks if t['rombel'] == rombel_name]
            for d in range(num_days):
                for h in range(1, self.max_hours + 1):
                    overlapping = []
                    for t in rombel_tasks:
                        t_id = t['id']
                        dur = t['duration']
                        for start_h in range(max(1, h - dur + 1), h + 1):
                            if (t_id, d, start_h) in X:
                                overlapping.append(X[(t_id, d, start_h)])
                    if overlapping:
                        model.Add(sum(overlapping) <= 1)

        # 5. Constraint: Tidak Boleh Bentrok Guru
        guru_list = list(set(t['guru_id'] for t in tasks))
        for gid in guru_list:
            guru_tasks = [t for t in tasks if t['guru_id'] == gid]
            for d in range(num_days):
                for h in range(1, self.max_hours + 1):
                    overlapping = []
                    for t in guru_tasks:
                        t_id = t['id']
                        dur = t['duration']
                        for start_h in range(max(1, h - dur + 1), h + 1):
                            if (t_id, d, start_h) in X:
                                overlapping.append(X[(t_id, d, start_h)])
                    if overlapping:
                        model.Add(sum(overlapping) <= 1)

        # 6. Jalankan Solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.num_search_workers = 4
        
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            records = []
            
            # Tambahkan entri khusus Upacara di Hari Senin Jam ke-1 untuk semua kelas
            if 'Senin' in self.days:
                for r in rombel_list:
                    records.append({
                        'Hari': 'Senin',
                        'Jam_Ke': 1,
                        'Rombel': r,
                        'Mapel': 'Upacara',
                        'Guru': '-'
                    })

            # Masukkan hasil dari solver
            for t in tasks:
                t_id = t['id']
                dur = t['duration']
                gid = t['guru_id']
                display_guru = guru_info.get(gid, {}).get('display_name', gid)

                for d in range(num_days):
                    for h in range(1, self.max_hours - dur + 2):
                        if (t_id, d, h) in X and solver.Value(X[(t_id, d, h)]) == 1:
                            for offset in range(dur):
                                records.append({
                                    'Hari': self.days[d],
                                    'Jam_Ke': h + offset,
                                    'Rombel': t['rombel'],
                                    'Mapel': t['mapel'],
                                    'Guru': display_guru
                                })
            
            df_res = pd.DataFrame(records)
            df_res.sort_values(by=['Hari', 'Jam_Ke', 'Rombel'], inplace=True)
            self.results_df = df_res
            self.assignments = records
            return True
        else:
            return False

    def extract_results(self):
        return self.results_df

    def get_schedule(self):
        return self.results_df

    def generate_teacher_report(self, df_hasil):
        if df_hasil.empty:
            return pd.DataFrame()
        
        df_valid = df_hasil[df_hasil['Guru'] != '-']
        rekap = df_valid.groupby(['Guru', 'Hari']).agg(
            Total_JP=('Jam_Ke', 'count'),
            Detail_Mengajar=('Jam_Ke', lambda x: f"Jam {min(x)}-{max(x)}")
        ).reset_index()
        
        rekap.rename(columns={'Guru': 'ID_Guru_Nama'}, inplace=True)
        return rekap
