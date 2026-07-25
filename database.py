import pandas as pd

class DatabaseLoader:
    def __init__(self, file_path="database_scheduler.xlsx"):
        self.file_path = file_path
        self.guru_df = None
        self.mapel_df = None
        self.rombel_df = None
        self.guru_mengajar_df = None
        self.slot_df = None

    def load_all(self):
        xls = pd.ExcelFile(self.file_path)
        
        self.guru_df = pd.read_excel(xls, 'Guru')
        self.mapel_df = pd.read_excel(xls, 'Mapel')
        self.rombel_df = pd.read_excel(xls, 'Rombel')
        self.guru_mengajar_df = pd.read_excel(xls, 'Guru_Mengajar')
        self.slot_df = pd.read_excel(xls, 'Slot')

        # Parsing slot string "2,2,1" menjadi list integer [2, 2, 1]
        def parse_slot_str(val):
            if pd.isna(val):
                return []
            return [int(x.strip()) for x in str(val).split(',') if x.strip().isdigit()]

        self.guru_mengajar_df['Slot_List'] = self.guru_mengajar_df['Slot'].apply(parse_slot_str)
        
        # PERBAIKAN UTAMA: Filter jenis slot 'PEMBELAJARAN' atau 'KBM' & pastikan Jam tidak kosong (bukan Istirahat/Upacara)
        if 'Jenis' in self.slot_df.columns:
            valid_types = ['PEMBELAJARAN', 'KBM']
            self.kbm_slots = self.slot_df[
                self.slot_df['Jenis'].astype(str).str.strip().str.upper().isin(valid_types)
            ].copy()
        else:
            self.kbm_slots = self.slot_df.copy()

        # Pastikan kolom Jam berupa integer dan hapus nilai NaN (seperti jam Istirahat)
        self.kbm_slots = self.kbm_slots.dropna(subset=['Jam'])
        self.kbm_slots['Jam'] = self.kbm_slots['Jam'].astype(int)

        return {
            'guru': self.guru_df,
            'mapel': self.mapel_df,
            'rombel': self.rombel_df,
            'guru_mengajar': self.guru_mengajar_df,
            'slot': self.slot_df,
            'kbm_slots': self.kbm_slots
        }

    # Alias untuk kompatibilitas
    load_data = load_all

if __name__ == "__main__":
    db = DatabaseLoader()
    data = db.load_all()
    print(f"✅ Slot Pembelajaran ditemukan: {len(data['kbm_slots'])} slot")
