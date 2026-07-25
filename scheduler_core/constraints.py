import re

class ScheduleConstraints:
    def __init__(self, guru_df, slot_df):
        if 'ID Guru' in guru_df.columns and 'Hari MGMP' in guru_df.columns:
            self.mgmp_days = dict(zip(guru_df['ID Guru'], guru_df['Hari MGMP'].fillna('')))
        else:
            self.mgmp_days = {}
        
    def is_teacher_available(self, guru_id, hari):
        """Memastikan guru tidak mengajar di hari MGMP-nya."""
        mgmp_day = self.mgmp_days.get(guru_id, '')
        if str(mgmp_day).strip().lower() == str(hari).strip().lower():
            return False
        return True

    def is_slot_free(self, schedule_board, hari, jam_start, block_size, guru_id, kelas):
        """Memastikan guru dan kelas tidak bentrok pada slot yang sama."""
        for offset in range(block_size):
            jam_check = jam_start + offset
            slot_key = (hari, jam_check)
            
            if slot_key in schedule_board:
                for entry in schedule_board[slot_key]:
                    if entry['guru_id'] == guru_id or entry['kelas'] == kelas:
                        return False
        return True

    def is_daily_limit_exceeded(self, schedule_board, hari, guru_id, kelas, mapel, block_size):
        """
        VALIDASI:
        Maksimal mengajar mapel yang sama di kelas yang sama adalah 2 JP per hari,
        KECUALI jika block_size / total JP mapel tersebut = 3.
        """
        if block_size == 3:
            # Jika alokasi jam memang 3 JP sekaligus, izinkan
            return False

        existing_jp = 0
        for (h, _), entries in schedule_board.items():
            if h == hari:
                for entry in entries:
                    if entry['guru_id'] == guru_id and entry['kelas'] == kelas and entry['mapel'] == mapel:
                        existing_jp += 1

        # Jika sudah ada jam sebelumnya dan total penambahan melebihi 2 JP
        if (existing_jp + block_size) > 2:
            return True
        return False


ConstraintManager = ScheduleConstraints
