import pandas as pd

def convert_schedule_to_database(excel_path="database_scheduler.xlsx", output_path="database_scheduler_ready.xlsx"):
    xls = pd.ExcelFile(excel_path)
    sheet_names = xls.sheet_names
    
    print(f"📄 Sheet yang terdeteksi: {sheet_names}")
    
    # 1. GENERATE DATA ROMBEL (15 Kelas)
    kelas_sheets = [s for s in sheet_names if s.startswith('Kelas_')]
    if not kelas_sheets and 'Jadwal_Semua_Kelas' in sheet_names:
        # Jika hanya ada Jadwal_Semua_Kelas, pakai sheet itu
        df_all = pd.read_excel(xls, 'Jadwal_Semua_Kelas')
    
    rombel_data = []
    for idx, ks in enumerate(kelas_sheets, start=1):
        nama_kelas = ks.replace('Kelas_', '')
        rombel_data.append({'Rombel_ID': nama_kelas, 'Nama_Rombel': f"Kelas {nama_kelas}"})
    
    rombel_df = pd.DataFrame(rombel_data)
    
    # 2. GENERATE DATA SLOT (41 JP KBM: Sen-Kam 9 JP, Jum 5 JP)
    slot_data = []
    hari_list = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    slot_id = 1
    
    for hari in hari_list:
        max_jam = 5 if hari == 'Jumat' else 9
        for jam in range(1, max_jam + 1):
            slot_data.append({
                'Slot_ID': slot_id,
                'Hari': hari,
                'Jam': jam,
                'Jenis': 'KBM'
            })
            slot_id += 1
            
    slot_df = pd.DataFrame(slot_data)
    
    # 3. EXTRACTION DATA GURU & GURU_MENGAJAR DARI SHEET KELAS
    guru_set = set()
    guru_mengajar_list = []
    mapel_set = set()
    
    for ks in kelas_sheets:
        rombel_id = ks.replace('Kelas_', '')
        df_kelas = pd.read_excel(xls, ks)
        
        # Cari kolom yang berisi info Guru/Mapel di sheet tersebut
        # Asumsi umum: Sel berisi format "Mapel - Nama Guru" atau "Nama Guru (Mapel)"
        for col in df_kelas.columns:
            for val in df_kelas[col].dropna():
                val_str = str(val).strip()
                if val_str and val_str.upper() not in ['HARI', 'JAM', 'ISTIRAHAT', 'UPACARA']:
                    # Coba split jika ada pemisah (-)
                    if '-' in val_str:
                        parts = val_str.split('-')
                        mapel = parts[0].strip()
                        guru = parts[1].strip()
                    else:
                        mapel = "MAPEL_UMUM"
                        guru = val_str
                    
                    guru_set.add(guru)
                    mapel_set.add(mapel)
                    
                    guru_mengajar_list.append({
                        'Guru_ID': guru,
                        'Rombel_ID': rombel_id,
                        'Mapel_ID': mapel,
                        'JP': 1
                    })

    # Grouping Guru_Mengajar agar JP terakumulasi per Guru & Rombel
    if guru_mengajar_list:
        gm_df = pd.DataFrame(guru_mengajar_list)
        gm_df = gm_df.groupby(['Guru_ID', 'Rombel_ID', 'Mapel_ID'], as_index=False).sum()
    else:
        gm_df = pd.DataFrame(columns=['Guru_ID', 'Rombel_ID', 'Mapel_ID', 'JP'])

    guru_df = pd.DataFrame([{'Guru_ID': g, 'Nama_Guru': g} for g in guru_set])
    mapel_df = pd.DataFrame([{'Mapel_ID': m, 'Nama_Mapel': m} for m in mapel_set])

    # 4. SIMPAN KE FILE EXCEL DATABASE BARU
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        guru_df.to_excel(writer, sheet_name='Guru', index=False)
        mapel_df.to_excel(writer, sheet_name='Mapel', index=False)
        rombel_df.to_excel(writer, sheet_name='Rombel', index=False)
        gm_df.to_excel(writer, sheet_name='Guru_Mengajar', index=False)
        slot_df.to_excel(writer, sheet_name='Slot', index=False)
        
    print(f"✅ BERHASIL! File database siap pakai telah dibuat: '{output_path}'")
    print(f"📊 Ringkasan Data: {len(guru_df)} Guru | {len(rombel_df)} Rombel | {len(gm_df)} Alokasi Mengajar")

if __name__ == "__main__":
    convert_schedule_to_database()
