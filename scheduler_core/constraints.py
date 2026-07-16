# scheduler_core/constraints.py

class ConstraintBuilder:
    def __init__(self, solver_engine):
        self.se = solver_engine
        self.model = solver_engine.model
        self.x = solver_engine.x
        
        # Mengambil data pembantu dari engine
        self.mengajar = se.mengajar
        self.slot = se.slot
        self.rombel = se.rombel
        self.guru = se.guru

    def apply_all(self):
        """Menjalankan semua fungsi batasan (constraints) pada model CP-SAT"""
        self.constraint_satu_guru_satu_kelas()
        self.constraint_satu_kelas_satu_guru()
        self.constraint_pagu_mengajar()

    def constraint_satu_guru_satu_kelas(self):
        """Memastikan seorang Guru tidak mengajar di 2 kelas berbeda pada slot waktu yang sama"""
        for g_id in self.guru["ID_Guru"]:
            for s_idx in self.slot.index:
                # Cari baris mengajar yang melibatkan guru ini
                baris_mengajar = self.mengajar[self.mengajar["ID_Guru"] == g_id].index
                
                # Guru hanya boleh berada di maksimal 1 kelas pada slot waktu s_idx
                self.model.AddAtMostOne(self.x[m_idx, s_idx] for m_idx in baris_mengajar)

    def constraint_satu_kelas_satu_guru(self):
        """Memastikan sebuah Rombel/Kelas hanya diisi oleh maksimal 1 Guru pada slot waktu yang sama"""
        for r_id in self.rombel["ID_Rombel"]:
            for s_idx in self.slot.index:
                # Cari baris mengajar yang ditujukan untuk kelas ini
                baris_mengajar = self.mengajar[self.mengajar["ID_Rombel"] == r_id].index
                
                # Kelas hanya boleh menerima maksimal 1 sesi mengajar pada slot waktu s_idx
                self.model.AddAtMostOne(self.x[m_idx, s_idx] for m_idx in baris_mengajar)

    def constraint_pagu_mengajar(self):
        """Memastikan jumlah jam mengajar (JP) setiap tugas guru sesuai dengan kuota di Excel"""
        for m_idx, row in self.mengajar.iterrows():
            target_jp = int(row[self.se.col_jp])
            
            # Total slot waktu yang dialokasikan untuk baris mengajar ini harus sama dengan target JP
            self.model.Add(
                sum(self.x[m_idx, s_idx] for s_idx in self.slot.index) == target_jp
            )
