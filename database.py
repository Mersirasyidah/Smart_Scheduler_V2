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
        
        # Filter hanya slot jam pelajaran KBM (abaikan Upacara & Istirahat)
        if 'Jenis' in self.slot_df.columns:
            self.kbm_slots = self.slot_df[self.slot_df['Jenis'].astype(str).str.upper() == 'KBM'].copy()
        else:
            self.kbm_slots = self.slot_df.copy()

        return {
            'guru': self.guru_df,
            'mapel': self.mapel_df,
            'rombel': self.rombel_df,
            'guru_mengajar': self.guru_mengajar_df,
            'slot': self.slot_df,
            'kbm_slots': self.kbm_slots
        }

    # Alias untuk kompatibilitas jika ada kode lama yang memanggil load_data()
    load_data = load_all

if __name__ == "__main__":
    db = DatabaseLoader()
    data = db.load_all()
    print("Database berhasil dimuat!")
