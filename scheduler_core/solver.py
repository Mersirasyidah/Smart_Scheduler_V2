from scheduler_core.constraints import ScheduleConstraints

class SchedulerSolver:
    def __init__(self, db_data):
        self.guru_mengajar = db_data['guru_mengajar']
        self.kbm_slots = db_data['kbm_slots']
        self.constraints = ScheduleConstraints(db_data['guru'], db_data['slot'])
        
        self.days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
        self.slots_by_day = {}
        for day in self.days:
            self.slots_by_day[day] = self.kbm_slots[self.kbm_slots['Hari'] == day]['Jam'].tolist()

    def solve(self):
        schedule_board = {} 
        unassigned = []

        records = self.guru_mengajar.to_dict(orient='records')

        # Prioritaskan pengalokasian: PJOK dulu, lalu blok jam terbesar (3 JP, 2 JP)
        def priority_key(item):
            mapel = str(item['Mapel']).lower()
            is_pjok = 'jasmani' in mapel or 'olahraga' in mapel or 'pjok' in mapel
            jp = item.get('JP', 0)
            return (0 if is_pjok else 1, -jp)

        records.sort(key=priority_key)

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
                        
                    available_jams = self.slots_by_day.get(day, [])
                    for jam in available_jams:
                        # Cek apakah cukup jam berturut-turut
                        if all((jam + offset) in available_jams for offset in range(block_size)):
                            
                            # Cek Aturan PJOK
                            if not self.constraints.is_pjok_valid(mapel, kelas, day, jam):
                                continue

                            # Cek Bentrok Slot
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
