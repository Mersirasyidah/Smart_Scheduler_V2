import pandas as pd

class DatabaseLoader:
    def __init__(self, excel_path="database_scheduler.xlsx"):
        self.excel_path = excel_path
        self.guru_df = None
        self.mapel_df = None
        self.rombel_df = None
        self.guru_mengajar_df = None
        self.slot_df = None

    def load_data(self):
        xls = pd.ExcelFile(self.excel_path)
        
        self.guru_df = pd.read_excel(xls, 'Guru')
        self.mapel_df = pd.read_excel(xls, 'Mapel')
        self.rombel_df = pd.read_excel(xls, 'Rombel')
        self.guru_mengajar_df = pd.read_excel(xls, 'Guru_Mengajar')
        self.slot_df = pd.read_excel(xls, 'Slot')

        # Preprocessing kolom Slot ("2,2,1" -> [2, 2, 1])
        if 'Slot' in self.guru_mengajar_df.columns:
            self.guru_mengajar_df['Slot_List'] = self.guru_mengajar_df['Slot'].apply(
                lambda x: [int(i.strip()) for i in str(x).split(',')] if pd.notna(x) else []
            )

        print(" Data Excel Berhasil Dimuat!")
        return {
            'guru': self.guru_df,
            'mapel': self.mapel_df,
            'rombel': self.rombel_df,
            'guru_mengajar': self.guru_mengajar_df,
            'slot': self.slot_df
        }

if __name__ == "__main__":
    db = DatabaseLoader()
    data = db.load_data()
    print(f"Total Alokasi Mengajar: {len(data['guru_mengajar'])} data")
