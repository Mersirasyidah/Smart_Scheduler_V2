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

    def is_pjok_valid(self, mapel, kelas, hari, jam_start):
        """
        VALIDASI KHUSUS PJOK (M11 / Olahraga):
        - Kelas 7 & 8: Jam 1-3 (Khusus Senin Jam 2-4)
        - Kelas 9    : Jam 4-6
        """
        mapel_str = str(mapel).lower()
        is_pjok = 'jasmani' in mapel_str or 'olahraga' in mapel_str or 'pjok' in mapel_str or 'm11' in mapel_str
        
        if not is_pjok:
            return True

        tingkat = str(kelas)[0] if str(kelas)[0].isdigit() else ''
        
        if tingkat in ['7', '8']:
            if hari == 'Senin':
                return jam_start == 2
            else:
                return jam_start == 1
        elif tingkat == '9':
            return jam_start == 4
            
        return True

ConstraintManager = ScheduleConstraints
