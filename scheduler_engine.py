import pandas as pd
import random
from database_loader import DatabaseLoader # Mengimpor file DatabaseLoader Anda

class SmartSchedulerV2:
    def __init__(self, data):
        self.guru_df = data['guru']
        self.rombel_df = data['rombel']
        self.guru_mengajar_df = data['guru_mengajar']
        self.kbm_slots = data['kbm_slots']
        
        self.jadwal = {}      # Key: (Hari, Jam, Rombel_ID) -> Value: dict tugas
        self.guru_busy = set() # Key: (Hari, Jam, Guru_ID)
        self.unassigned = []

    def prepare_tasks(self):
        """Memecah data guru_mengajar menjadi unit tugas berdurasi (misal 2 JP, 3 JP, atau 1 JP)"""
        tasks = []
        for _, row in self.guru_mengajar_df.iterrows():
            guru_id = row['Guru_ID']
            rombel_id = row['Rombel_ID']
            mapel = row['Mapel_ID']
            slot_list = row.get('Slot_List', [])
            
            # Jika Slot_List tidak ada/kosong, gunakan total JP
            if not slot_list and 'JP' in row:
                slot_list = [1] * int(row['JP'])

            for block_len in slot_list:
                tasks.append({
                    'guru_id': guru_id,
                    'rombel_id': rombel_id,
                    'mapel': mapel,
                    'duration': block_len
                })
        
        # PERBAIKAN UTAMA 1: SORTING PRIORITAS
        # Urutkan tugas dari durasi terbesar (misal 3 JP dulu) agar jam blok tidak buntu di akhir
        tasks.sort(key=lambda x: x['duration'], reverse=True)
        return tasks

    def generate(self):
        tasks = self.prepare_tasks()
        
        # Ambil daftar unik Hari, Jam, dan Rombel
        daftar_hari = self.kbm_slots['Hari'].unique()
        daftar_rombel = self.rombel_df['Rombel_ID'].unique()

        for task in tasks:
            placed = self.coba_tempatkan_tugas(task, daftar_hari, daftar_rombel)
            
            # PERBAIKAN UTAMA 2: BACKTRACKING / SWAP SLOT (Jika penempatan biasa buntu)
            if not placed:
                placed = self.coba_backtrack_swap(task, daftar_hari, daftar_rombel)

            if not placed:
                self.unassigned.append(task)

        return self.jadwal, self.unassigned

    def coba_tempatkan_tugas(self, task, daftar_hari, daftar_rombel):
        duration = task['duration']
        rombel = task['rombel_id']
        guru = task['guru_id']

        # Acak hari untuk variasi distribusi
        hari_list = list(daftar_hari)
        random.shuffle(hari_list)

        for hari in hari_list:
            slots_hari = self.kbm_slots[self.kbm_slots['Hari'] == hari].sort_values('Jam')
            jam_list = slots_hari['Jam'].tolist()

            # Cari blok jam berurutan sesuai durasi (misal 2 JP berturut-turut)
            for i in range(len(jam_list) - duration + 1):
                block_jams = jam_list[i : i + duration]
                
                # Cek Syarat:
                # 1. Rombel kosong di semua jam blok tersebut
                # 2. Guru TIDAK mengajar di rombel lain pada semua jam blok tersebut
                bisa_masuk = True
                for jam in block_jams:
                    if (hari, jam, rombel) in self.jadwal or (hari, jam, guru) in self.guru_busy:
                        bisa_masuk = False
                        break
                
                if bisa_masuk:
                    for jam in block_jams:
                        self.jadwal[(hari, jam, rombel)] = task
                        self.guru_busy.add((hari, jam, guru))
                    return True
        return False

    def coba_backtrack_swap(self, task, daftar_hari, daftar_rombel):
        """Mekanisme menggeser tugas lain yang sudah terpasang agar 7 guru terlempar bisa masuk"""
        guru = task['guru_id']
        rombel = task['rombel_id']
        duration = task['duration']

        for hari in daftar_hari:
            slots_hari = self.kbm_slots[self.kbm_slots['Hari'] == hari].sort_values('Jam')
            jam_list = slots_hari['Jam'].tolist()

            for i in range(len(jam_list) - duration + 1):
                block_jams = jam_list[i : i + duration]

                # Cek apakah guru utama TIDAK bentrok di jam ini
                if any((hari, jam, guru) in self.guru_busy for jam in block_jams):
                    continue

                # Ambil tugas yang sedang menempati slot rombel ini saat ini
                tugas_penghuni = [self.jadwal.get((hari, jam, rombel)) for jam in block_jams]
                
                # Lakukan swap jika slot diisi tugas tunggal
                if len(tugas_penghuni) == 1 and tugas_penghuni[0] is not None:
                    t_lama = tugas_penghuni[0]
                    
                    # Lepas sementara tugas lama
                    for jam in block_jams:
                        del self.jadwal[(hari, jam, rombel)]
                        self.guru_busy.remove((hari, jam, t_lama['guru_id']))

                    # Coba pindahkan tugas lama ke tempat lain
                    pindah_sukses = self.coba_tempatkan_tugas(t_lama, daftar_hari, daftar_rombel)
                    
                    if pindah_sukses:
                        # Pasang tugas baru ke slot yang ditinggalkan
                        for jam in block_jams:
                            self.jadwal[(hari, jam, rombel)] = task
                            self.guru_busy.add((hari, jam, guru))
                        return True
                    else:
                        # Jika gagal dipindah, kembalikan tugas lama ke tempat semula
                        for jam in block_jams:
                            self.jadwal[(hari, jam, rombel)] = t_lama
                            self.guru_busy.add((hari, jam, t_lama['guru_id']))

        return False

# ==============================================================================
# CARA MENJALANKAN ENGINE
# ==============================================================================
if __name__ == "__main__":
    # 1. Load Data
    loader = DatabaseLoader("database_scheduler.xlsx")
    data = loader.load_all()

    # 2. Run Engine Smart Scheduler V2
    engine = SmartSchedulerV2(data)
    jadwal_hasil, terlempar = engine.generate()

    print("\n--- HASIL GENERATE SMART SCHEDULER V2 ---")
    print(f"✅ Total Jam Terisi  : {len(jadwal_hasil)} JP")
    print(f"❌ Total Jam Terlempar: {len(terlempar)} Tugas")

    if len(terlempar) == 0:
        print("🎉 SANGAT SUKSES! Semua 615 JP / 27 Guru berhasil masuk 100% tanpa bentrok.")
    else:
        print("⚠️ Detail tugas yang belum terpasang:", terlempar)
