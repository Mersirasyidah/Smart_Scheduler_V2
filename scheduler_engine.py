import pandas as pd
import random
from database_loader import DatabaseLoader

class SmartSchedulerV2:
    def __init__(self, data):
        self.guru_df = data['guru']
        self.rombel_df = data['rombel']
        self.guru_mengajar_df = data['guru_mengajar']
        self.kbm_slots = data['kbm_slots']
        
        self.jadwal = {}       # Key: (Hari, Jam, Rombel_ID) -> Value: dict tugas
        self.guru_busy = set() # Key: (Hari, Jam, Guru_ID)
        self.unassigned = []

    def prepare_unit_tasks(self):
        """
        Memecah semua tugas menjadi satuan 1-JP tunggal.
        Ini menjamin perhitungan slot murni 1 banding 1 hingga mencapai total 615 JP.
        """
        tasks = []
        for _, row in self.guru_mengajar_df.iterrows():
            guru_id = row['Guru_ID']
            rombel_id = row['Rombel_ID']
            mapel = row['Mapel_ID']
            
            # Ambil total JP dari baris Excel
            jp_total = int(row['JP']) if 'JP' in row and pd.notna(row['JP']) else 0
            
            # Jika menggunakan Slot_List, hitung total JP dari sum
            slot_list = row.get('Slot_List', [])
            if slot_list:
                jp_total = sum(slot_list)

            # Buat unit tugas tunggal (1 JP per entri)
            for i in range(jp_total):
                tasks.append({
                    'id': f"{guru_id}_{rombel_id}_{mapel}_{i}",
                    'guru_id': guru_id,
                    'rombel_id': rombel_id,
                    'mapel': mapel,
                    'total_guru_jp': jp_total # Dipakai untuk prioritas sorting
                })
        
        # PERBAIKAN 1: PRIORITAS SORTING
        # Guru dengan beban JP paling besar diproses lebih awal
        tasks.sort(key=lambda x: x['total_guru_jp'], reverse=True)
        return tasks

    def generate(self):
        tasks = self.prepare_unit_tasks()
        
        daftar_hari = list(self.kbm_slots['Hari'].unique())
        daftar_rombel = list(self.rombel_df['Rombel_ID'].unique())

        for task in tasks:
            # Langkah 1: Coba alokasi biasa ke slot kosong
            placed = self.coba_tempatkan_unit(task, daftar_hari)
            
            # Langkah 2: Jika terbentur, jalankan SWAP / BACKTRACKING
            if not placed:
                placed = self.coba_backtrack_swap_unit(task, daftar_hari)

            if not placed:
                self.unassigned.append(task)

        return self.jadwal, self.unassigned

    def coba_tempatkan_unit(self, task, daftar_hari):
        rombel = task['rombel_id']
        guru = task['guru_id']

        hari_list = list(daftar_hari)
        random.shuffle(hari_list) # Mencegah penumpukan di hari Senin

        for hari in hari_list:
            slots_hari = self.kbm_slots[self.kbm_slots['Hari'] == hari].sort_values('Jam')
            jam_list = slots_hari['Jam'].tolist()

            for jam in jam_list:
                key_jadwal = (hari, jam, rombel)
                key_guru = (hari, jam, guru)

                # Syarat: Slot kelas KOSONG & Guru TIDAK MENGANJAR di rombel lain pada jam tersebut
                if key_jadwal not in self.jadwal and key_guru not in self.guru_busy:
                    self.jadwal[key_jadwal] = task
                    self.guru_busy.add(key_guru)
                    return True
        return False

    def coba_backtrack_swap_unit(self, task, daftar_hari):
        """
        Menggeser 1 JP guru lain yang sudah terpasang ke slot kosong lain
        agar slotnya bisa dipakai oleh tugas yang terhalang.
        """
        guru_butuh = task['guru_id']
        rombel_butuh = task['rombel_id']

        for hariA in daftar_hari:
            slots_hariA = self.kbm_slots[self.kbm_slots['Hari'] == hariA].sort_values('Jam')
            for jamA in slots_hariA['Jam'].tolist():
                
                key_guruA = (hariA, jamA, guru_butuh)
                key_jadwalA = (hariA, jamA, rombel_butuh)

                # Jika guru yang mau masuk TIDAK BENTROK di jamA
                if key_guruA not in self.guru_busy and key_jadwalA in self.jadwal:
                    tugas_penghuni = self.jadwal[key_jadwalA]
                    guru_penghuni = tugas_penghuni['guru_id']

                    # Lepas sementara tugas penghuni lama
                    del self.jadwal[key_jadwalA]
                    self.guru_busy.remove((hariA, jamA, guru_penghuni))

                    # Coba cari slot kosong alternatif untuk tugas penghuni lama
                    pindah_sukses = self.coba_tempatkan_unit(tugas_penghuni, daftar_hari)

                    if pindah_sukses:
                        # Masukkan tugas baru ke slot yang sudah dikosongkan
                        self.jadwal[key_jadwalA] = task
                        self.guru_busy.add(key_guruA)
                        return True
                    else:
                        # Kembalikan penghuni lama jika tidak menemukan slot alternatif
                        self.jadwal[key_jadwalA] = tugas_penghuni
                        self.guru_busy.add((hariA, jamA, guru_penghuni))

        return False

# ==============================================================================
# EKSEKUSI ENGINE
# ==============================================================================
if __name__ == "__main__":
    loader = DatabaseLoader("database_scheduler.xlsx")
    data = loader.load_all()

    engine = SmartSchedulerV2(data)
    jadwal_hasil, terlempar = engine.generate()

    print("\n================ HASIL AKHIR SCHEDULER ================")
    print(f"📊 Total Slot Terisi  : {len(jadwal_hasil)} / 615 JP")
    print(f"❌ Total JP Terlempar : {len(terlempar)} JP")
    print("=======================================================")

    if len(jadwal_hasil) == 615:
        print("🎉 SUKSES PRESISI 100%! Semua 615 JP berhasil terplot sempurna.")
    else:
        print(f"⚠️ Masih ada {615 - len(jadwal_hasil)} JP yang belum terisi.")
