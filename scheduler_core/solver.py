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

    def parse_slot_pattern(self, slot_val, total_jp):
        """Memecah kolom Slot (misal '2,2,1' atau '2+2+1') menjadi list durasi [2, 2, 1]"""
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
            # Fallback jika penjumlahan slot tidak sama dengan Total JP
            blocks = []
            sisa = total_jp
            while sisa > 0:
                take = 2 if sisa >= 2 else 1
                blocks.append(take)
                sisa -= take

        return blocks if len(blocks) > 0 else [total_jp]

    def solve(self, time_limit=120):
        model = cp_model.CpModel()
        
        # Identifikasi kolom secara fleksibel
        col_guru = next((c for c in self.mengajar_df.columns if 'guru' in c.lower()), 'Guru')
        col_rombel = next((c for c in self.mengajar_df.columns if 'rombel' in c.lower() or 'kelas' in c.lower()), 'Rombel')
        col_mapel = next((c for c in self.mengajar_df.columns if 'mapel' in c.lower()), 'Mapel')
        col_jp = next((c for c in self.mengajar_df.columns if 'jp' in c.lower() or 'jam' in c.lower()), 'Beban_JP')
        col_slot = next((c for c in self.mengajar_df.columns if 'slot' in c.lower() or 'pembagian' in c.lower()), 'Slot')

        # 1. Breakout Task Mengajar
        tasks = []
        task_id = 0
        for _, row in self.mengajar_df.iterrows():
            guru = str(row[col_guru])
            rombel = str(row[col_rombel])
            mapel = str(row[col_mapel])
            try:
                total_jp = int(row[col_jp])
            except (ValueError, TypeError):
                continue
            
            slot_val = row.get(col_slot, None)
            durations = self.parse_slot_pattern(slot_val, total_jp)

            for dur in durations:
                tasks.append({
                    'id': task_id,
                    'guru': guru,
                    'rombel': rombel,
                    'mapel': mapel,
                    'duration': dur
                })
                task_id += 1

        if not tasks:
            return False

        # 2. Variable Decision: X[task_id, day_idx, hour_start]
        num_days = len(self.days)
        X = {}
        
        for t in tasks:
            t_id = t['id']
            dur = t['duration']
            for d in range(num_days):
                for h in range(1, self.max_hours - dur + 2):
                    X[(t_id, d, h)] = model.NewBoolVar(f'x_{t_id}_{d}_{h}')

        # 3. HARD CONSTRAINT 1: Setiap task harus dijadwalkan TEPAT 1 KALI
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

        # 4. HARD CONSTRAINT 2: Rombel tidak boleh bentrok (1 slot jam cuma 1 mapel)
        for rombel_name in self.rombel_df.iloc[:, 0].astype(str).unique():
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

        # 5. HARD CONSTRAINT 3: Guru tidak boleh mengajar di 2 kelas berbeda pada jam yang sama
        for guru_name in self.guru_df.iloc[:, 0].astype(str).unique():
            guru_tasks = [t for t in tasks if t['guru'] == guru_name]
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

        # --- JALANKAN SOLVER ---
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.num_search_workers = 4  # Menggunakan multi-core CPU
        
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            records = []
            for t in tasks:
                t_id = t['id']
                dur = t['duration']
                for d in range(num_days):
                    for h in range(1, self.max_hours - dur + 2):
                        if (t_id, d, h) in X and solver.Value(X[(t_id, d, h)]) == 1:
                            for slot_offset in range(dur):
                                records.append({
                                    'Hari': self.days[d],
                                    'Jam_Ke': h + slot_offset,
                                    'Rombel': t['rombel'],
                                    'Mapel': t['mapel'],
                                    'Guru': t['guru']
                                })
            
            self.results_df = pd.DataFrame(records)
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
        
        # Rekap harian per guru
        rekap = df_hasil.groupby(['Guru', 'Hari']).agg(
            Total_JP=('Jam_Ke', 'count'),
            Detail_Mengajar=('Jam_Ke', lambda x: f"Jam {min(x)}-{max(x)} (" + ", ".join(df_hasil.loc[x.index, 'Rombel'].unique()) + ")")
        ).reset_index()
        
        rekap.rename(columns={'Guru': 'ID_Guru'}, inplace=True)
        rekap['Status'] = 'Mengajar'
        rekap['Jam_Kosong_Sela'] = '-'
        return rekap
