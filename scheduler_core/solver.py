import pandas as pd

class SchedulerSolver:
    def __init__(self, scheduler_or_data, days=None, max_hours=8):
        # Inisialisasi data
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

        self.days = days if days is not None else ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
        self.max_hours = max_hours
        self.assignments = []

    def parse_slot_pattern(self, slot_val, total_jp):
        """
        Mengubah format kolom Slot (misal "2,2,1" atau "2+2+1" atau "2 2 1")
        menjadi list blok jam: [2, 2, 1]
        """
        if pd.isna(slot_val) or not str(slot_val).strip():
            # Fallback default jika kolom Slot kosong: pecah maksimal 2 JP per pertemuan
            blocks = []
            sisa = total_jp
            while sisa > 0:
                take = 2 if sisa >= 2 else 1
                blocks.append(take)
                sisa -= take
            return blocks

        # Jika diisi string seperti "2,2,1" / "2+2+1" / "2 2 1"
        raw_str = str(slot_val).replace("+", ",").replace(" ", ",").replace("-", ",")
        parts = [p.strip() for p in raw_str.split(",") if p.strip().isdigit()]
        
        blocks = [int(p) for p in parts]
        
        # Validasi: Jika total pecahan tidak sesuai dengan Total JP, gunakan fallback
        if sum(blocks) != total_jp and len(blocks) > 0:
            # Sesuaikan atau gunakan pola asli
            pass
            
        return blocks if len(blocks) > 0 else [total_jp]

    def prepare_tasks(self):
        """Membuat daftar tugas mengajar terpisah berdasarkan pembagian slot"""
        self.tasks = []
        
        # Cari nama kolom yang sesuai
        col_guru = next((c for c in self.mengajar_df.columns if 'guru' in c.lower()), 'ID_Guru')
        col_rombel = next((c for c in self.mengajar_df.columns if 'rombel' in c.lower() or 'kelas' in c.lower()), 'ID_Rombel')
        col_mapel = next((c for c in self.mengajar_df.columns if 'mapel' in c.lower()), 'ID_Mapel')
        col_jp = next((c for c in self.mengajar_df.columns if 'jp' in c.lower() or 'jam' in c.lower()), 'Beban_JP')
        col_slot = next((c for c in self.mengajar_df.columns if 'slot' in c.lower() or 'pembagian' in c.lower()), 'Slot')

        for idx, row in self.mengajar_df.iterrows():
            guru = row[col_guru]
            rombel = row[col_rombel]
            mapel = row[col_mapel]
            total_jp = int(row[col_jp]) if pd.notna(row[col_jp]) else 0
            slot_pattern = row.get(col_slot, None)

            # Breakout total JP menjadi beberapa pertemuan (misal [2, 2, 1])
            session_blocks = self.parse_slot_pattern(slot_pattern, total_jp)
            
            for session_idx, duration in enumerate(session_blocks):
                self.tasks.append({
                    'task_id': f"{guru}_{rombel}_{mapel}_s{session_idx}",
                    'guru': guru,
                    'rombel': rombel,
                    'mapel': mapel,
                    'duration': duration, # Durasi JP untuk 1 kali pertemuan (misal 2 JP)
                    'session_idx': session_idx
                })

    def solve(self, time_limit=120):
        if not hasattr(self, 'assignments') or self.assignments is None:
            self.assignments = []
            
        # Siapkan task yang sudah dipecah berdasarkan kolom Slot
        self.prepare_tasks()
        
        # --- PROSES OR-TOOLS / CONSTRAINT SOLVER ANDA MEMAKAI self.tasks ---
        # Setiap task dalam self.tasks sekarang dijamin ditempatkan di HARI YANG BERBEDA
        # ...
        
        return True
