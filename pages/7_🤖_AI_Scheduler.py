def get_sheet_df(xls, target_name):
    """Mencari dan membaca sheet secara fleksibel (case-insensitive)."""
    for sheet in xls.sheet_names:
        if sheet.strip().lower() == target_name.strip().lower():
            return pd.read_excel(xls, sheet)
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan di file Excel! Sheet yang ada: {xls.sheet_names}")

# --- LOGIKA PENYUSUNAN JADWAL (SOLVER) ---
def generate_schedule(excel_path):
    xls = pd.ExcelFile(excel_path)
    
    # Membaca sheet dengan aman
    guru_df = get_sheet_df(xls, 'Guru')
    slot_df = get_sheet_df(xls, 'Slot')
    gm_df = get_sheet_df(xls, 'Guru_Mengajar')

    # Pemetaan Hari MGMP Guru
    mgmp_days = {}
    if 'ID Guru' in guru_df.columns and 'Hari MGMP' in guru_df.columns:
        mgmp_days = dict(zip(guru_df['ID Guru'], guru_df['Hari MGMP'].fillna('')))

    # Filter Slot KBM saja
    valid_types = ['PEMBELAJARAN', 'KBM']
    kbm_slots = slot_df[slot_df['Jenis'].astype(str).str.strip().str.upper().isin(valid_types)].dropna(subset=['Jam']).copy()
    kbm_slots['Jam'] = kbm_slots['Jam'].astype(int)

    days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    slots_by_day = {d: kbm_slots[kbm_slots['Hari'] == d]['Jam'].tolist() for d in days}

    gm_df['Slot_List'] = gm_df['Slot'].apply(parse_slot_list)
    records = gm_df.to_dict(orient='records')

    # Priority sorting: PJOK dulu, lalu durasi JP terbesar
    def get_priority(item):
        mapel = str(item['Mapel']).lower()
        is_pjok = 'jasmani' in mapel or 'olahraga' in mapel or 'pjok' in mapel or 'm11' in mapel
        return (0 if is_pjok else 1, -item.get('JP', 0))

    records.sort(key=get_priority)

    schedule_board = {}
    unassigned = []

    for item in records:
        guru_id = item['ID Guru']
        guru_nama = item['Nama Guru']
        mapel = item['Mapel']
        kelas = item['Kelas']
        slot_blocks = item.get('Slot_List', [])

        for block_size in slot_blocks:
            placed = False
            for day in days:
                # 1. Cek Libur MGMP
                mgmp_day = str(mgmp_days.get(guru_id, '')).strip().lower()
                if mgmp_day == day.lower():
                    continue

                # 2. Cek Validasi Max 2 JP per hari di kelas yang sama (kecuali mapel 3 JP)
                if block_size != 3:
                    existing_jp = 0
                    for (h, _), entries in schedule_board.items():
                        if h == day:
                            for e in entries:
                                if e['guru_id'] == guru_id and e['kelas'] == kelas and e['mapel'] == mapel:
                                    existing_jp += 1
                    if (existing_jp + block_size) > 2:
                        continue

                available_jams = slots_by_day.get(day, [])
                for jam in available_jams:
                    # Cek kecukupan jam berturut-turut
                    if all((jam + offset) in available_jams for offset in range(block_size)):
                        
                        # 3. Validasi Khusus PJOK (M11)
                        is_pjok = 'jasmani' in str(mapel).lower() or 'olahraga' in str(mapel).lower() or 'pjok' in str(mapel).lower()
                        if is_pjok:
                            tingkat = str(kelas)[0] if str(kelas)[0].isdigit() else ''
                            if tingkat in ['7', '8']:
                                valid_jam = (jam == 2) if day == 'Senin' else (jam == 1)
                                if not valid_jam:
                                    continue
                            elif tingkat == '9':
                                if jam != 4:
                                    continue

                        # 4. Cek Bentrok Guru / Kelas
                        bentrok = False
                        for offset in range(block_size):
                            slot_key = (day, jam + offset)
                            if slot_key in schedule_board:
                                for e in schedule_board[slot_key]:
                                    if e['guru_id'] == guru_id or e['kelas'] == kelas:
                                        bentrok = True
                                        break
                            if bentrok:
                                break

                        if not bentrok:
                            for offset in range(block_size):
                                slot_key = (day, jam + offset)
                                if slot_key not in schedule_board:
                                    schedule_board[slot_key] = []
                                schedule_board[slot_key].append({
                                    'guru_id': guru_id,
                                    'nama_guru': guru_nama,
                                    'mapel': mapel,
                                    'kelas': kelas
                                })
                            placed = True
                            break
                if placed:
                    break

            if not placed:
                unassigned.append({
                    'guru_id': guru_id,
                    'kelas': kelas,
                    'mapel': mapel,
                    'block_size': block_size
                })

    # Konversi Hasil ke DataFrame Master List
    rows = []
    for (hari, jam), assignments in schedule_board.items():
        for item in assignments:
            nama_depan = clean_first_name(item['nama_guru'])
            mapel_singkat = MAPEL_SHORT.get(str(item['mapel']).strip(), str(item['mapel'])[:4])
            kode_mapel = MAPEL_TO_KODE.get(str(item['mapel']).strip(), 'MXX')

            rows.append({
                'Hari': hari,
                'Jam': jam,
                'Kelas': item['kelas'],
                'ID Guru': item['guru_id'],
                'Nama Guru Full': item['nama_guru'],
                'Nama Guru': nama_depan,
                'Mapel Full': item['mapel'],
                'Mapel Singkat': mapel_singkat,
                'Kode Mapel': kode_mapel
            })

    df_schedule = pd.DataFrame(rows)
    return df_schedule, unassigned
