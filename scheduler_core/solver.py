def periksa_total_jp(mengajar_df, slot_df):
    # Total slot pembelajaran yang tersedia dalam seminggu
    slot_pembelajaran = slot_df[slot_df['Jenis'].str.upper() == 'PEMBELAJARAN']
    max_slot_minggu = len(slot_pembelajaran)
    
    # 1. Cek Total JP per Rombel / Kelas
    jp_per_rombel = mengajar_df.groupby('Kelas')['JP'].sum()
    rombel_over = jp_per_rombel[jp_per_rombel > max_slot_minggu]
    
    if not rombel_over.empty:
        for kelas, total_jp in rombel_over.items():
            print(f"⚠️ Peringatan: Kelas {kelas} memiliki {total_jp} JP, padahal slot maksimal seminggu adalah {max_slot_minggu} JP!")
        return False

    # 2. Cek Kesesuaian Antara Kolom JP dan Kolom Pembagian
    for idx, row in mengajar_df.iterrows():
        jp = row['JP']
        pembagian_str = str(row['Pembagian']).strip()
        
        if ',' in pembagian_str:
            list_jp = [int(x) for x in pembagian_str.split(',') if x.strip().isdigit()]
        elif '.' in pembagian_str:
            list_jp = [int(x) for x in pembagian_str.split('.') if x.strip().isdigit()]
        else:
            try:
                list_jp = [int(float(pembagian_str))]
            except:
                list_jp = [jp]
                
        if sum(list_jp) != jp:
            print(f"⚠️ Peringatan di Baris {idx+2}: Mapel {row['Mapel']} Kelas {row['Kelas']} - Kolom JP ({jp}) tidak cocok dengan Kolom Pembagian ({pembagian_str})!")
            return False

    return True
