from scheduler_core.constraints import ScheduleConstraints

class SchedulerSolver:
    def __init__(self, db_data):
        self.guru_mengajar = db_data['guru_mengajar']
        self.kbm_slots = db_data['kbm_slots']
        self.constraints = ScheduleConstraints(db_data['guru'], db_data['slot'])
        
        self.days = self.kbm_slots['Hari'].unique()
        self.slots_by_day = {}
        for day in self.days:
            self.slots_by_day[day] = self.kbm_slots[self.kbm_slots['Hari'] == day]['Jam'].tolist()

    def solve(self):
        schedule_board = {} 
        unassigned = []

        records = self.guru_mengajar.to_dict(orient='records')

        for item in records:
            guru_id = item['ID Guru']
            guru_nama = item['Nama Guru']
            mapel = item['Mapel']
            kelas = item['Kelas']
            slot_blocks = item.get('Slot_List', [])

            for block_size in slot_blocks:
                placed = False
                
                for day in self.days:
                    if not self.constraints.is_teacher_available(guru_id, day):
                        continue
                    
                    # Cek aturan batas JP harian
                    if self.constraints.is_daily_limit_exceeded(schedule_board, day, guru_id, kelas, mapel, block_size):
                        continue
                        
                    available_jams = self.slots_by_day[day]
                    for jam in available_jams:
                        if all((jam + offset) in available_jams for offset in range(block_size)):
                            if self.constraints.is_slot_free(schedule_board, day, jam, block_size, guru_id, kelas):
                                for offset in range(block_size):
                                    slot_key = (day, jam + offset)
                                    if slot_key not in schedule_board:
                                        schedule_board[slot_key] = []
                                    schedule_board[slot_key].append({
                                        'guru_id': guru_id,
                                        'nama_guru': guru_nama,
                                        'mapel': mapel,
                                        'kelas': kelas
                                    })
                                placed = True
                                break
                    if placed:
                        break
                
                if not placed:
                    unassigned.append({
                        'guru_id': guru_id,
                        'kelas': kelas,
                        'mapel': mapel,
                        'block_size': block_size
                    })

        return schedule_board, unassigned
