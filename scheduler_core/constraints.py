class ScheduleConstraints:
    def __init__(self, guru_df, slot_df):
        # Map Hari MGMP per ID Guru
        self.mgmp_days = dict(zip(guru_df['ID Guru'], guru_df['Hari MGMP'].fillna('')))
        
    def is_teacher_available(self, guru_id, hari):
        """Memastikan guru tidak mengajar di hari MGMP-nya."""
        mgmp_day = self.mgmp_days.get(guru_id, '')
        if str(mgmp_day).strip().lower() == str(hari).strip().lower():
            return False
        return True

    def is_slot_free(self, schedule_board, hari, jam_start, block_size, guru_id, kelas):
        """Memastikan guru dan kelas tidak bentrok pada rentang jam berturut-turut."""
        for offset in range(block_size):
            jam_check = jam_start + offset
            slot_key = (hari, jam_check)
            
            # Cek jika slot sudah diisi oleh guru atau kelas yang sama
            if slot_key in schedule_board:
                for entry in schedule_board[slot_key]:
                    if entry['guru_id'] == guru_id:
                        return False  # Bentrok Guru
                    if entry['kelas'] == kelas:
                        return False  # Bentrok Kelas
        return True
