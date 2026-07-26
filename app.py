import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Generator Jadwal Kelas 7", page_icon="🏫", layout="wide")

st.title("🏫 AI Automatic Schedule Generator — Kelas 7 (7A - 7E)")
st.write("Sistem Plotting Jadwal Kelas 7 (Optimasi Bottleneck Guru & Multi-Pass Auto-Split).")

# --- SIDEBAR & FILE INPUT ---
st.sidebar.header("📁 Input Database")
uploaded_file = st.sidebar.file_uploader("Upload File Database Excel", type=["xlsx", "xls"])
target_file_path = st.sidebar.text_input("Atau ketik jalur file lokal:", value="database_scheduler.xlsx")

input_data = uploaded_file if uploaded_file is not None else target_file_path

# --- MAPPING KODE MAPEL ---
MAPEL_TO_KODE = {
    'pendidikan jasmani olahraga dan kesehatan': 'M11', 'pjok': 'M11',
    'matematika': 'M07', 'mtk': 'M07',
    'ilmu pengetahuan alam': 'M08', 'ipa': 'M08',
    'ilmu pengetahuan sosial': 'M09', 'ips': 'M09',
    'informatika': 'M12', 'inf': 'M12',
    'prakarya': 'M14', 'prk': 'M14',
    'seni budaya': 'M13', 'snb': 'M13',
    'pendidikan pancasila': 'M05', 'pp': 'M05', 'pkn': 'M05',
    'bahasa jawa': 'M15', 'bjw': 'M15',
    'bahasa indonesia': 'M06', 'bin': 'M06',
    'bahasa inggris': 'M10', 'big': 'M10',
    'pendidikan agama islam': 'M01', 'pai': 'M01'
}

MAPEL_SHORT = {
    'pjok': 'PJOK', 'matematika': 'MTK', 'ilmu pengetahuan alam': 'IPA',
    'ilmu pengetahuan sosial': 'IPS', 'informatika': 'INF', 'prakarya': 'PRK',
    'seni budaya': 'SNB', 'pendidikan pancasila': 'PP', 'bahasa jawa': 'BJW',
    'bahasa indonesia': 'BIN', 'bahasa inggris': 'BIG', 'pendidikan agama islam': 'PAI', 'pai': 'PAI'
}

DAYS = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
DAY_INDEX = {day: idx for idx, day in enumerate(DAYS)}

def clean_first_name(nama_full):
    if pd.isna(nama_full): return ""
    clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
    words = clean_str.split()
    return words[0] if words else ""

def get_sheet_df(xls, target_name):
    target_clean = re.sub(r'[^a-zA-Z0-9]', '', str(target_name)).lower()
    for sheet in xls.sheet_names:
        sheet_clean = re.sub(r'[^a-zA-Z0-9]', '', str(sheet)).lower()
        if target_clean == sheet_clean or target_clean in sheet_clean:
            df = pd.read_excel(xls, sheet)
            df.columns = [str(c).strip() for c in df.columns]
            return df
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan! Sheet yang ada: {xls.sheet_names}.")

# --- ENGINE ATURAN KELAS 7 ---
def generate_schedule_kelas_7(excel_source):
    xls = pd.ExcelFile(excel_source)
    guru_df = get_sheet_df(xls, 'Guru')
    slot_df = get_sheet_df(xls, 'Slot')
    gm_df = get_sheet_df(xls, 'Guru_Mengajar')

    # Filter khusus kelas 7A - 7E
    target_kelas = ['7A', '7B', '7C', '7D', '7E']
    gm_df['Kelas'] = gm_df['Kelas'].astype(str).str.strip().str.upper()
    gm_df = gm_df[gm_df['Kelas'].isin(target_kelas)].copy()

    # ABAIKAN BK DAN AGAMA NON-ISLAM
    def is_valid_mapel(mapel_name):
        m = str(mapel_name).strip().lower()
        if 'bk' in m or 'bimbingan' in m or 'konseling' in m:
            return False
        if 'agama' in m and not ('islam' in m or 'pai' in m):
            return False
        return True

    gm_df = gm_df[gm_df['Mapel'].apply(is_valid_mapel)].copy()

    # Hitung Beban Mengajar per Guru (Untuk Prioritas Plotting Guru Padat)
    guru_workload = gm_df.groupby('ID Guru')['Kelas'].count().to_dict()

    # Bersihkan Data Slot KBM
    slot_df['Jam'] = pd.to_numeric(slot_df['Jam'], errors='coerce')
    slot_df = slot_df.dropna(subset=['Jam'])
    slot_df['Jam'] = slot_df['Jam'].astype(int)

    jenis_cols = [c for c in slot_df.columns if any(k in c.lower() for k in ['jenis', 'keterangan', 'kegiatan'])]
    if jenis_cols:
        j_col = jenis_cols[0]
        kbm_slots = slot_df[~slot_df[j_col].astype(str).str.upper().str.contains('ISTIRAHAT|UPACARA|PEMBIASAAN|SHOLAT')].copy()
    else:
        kbm_slots = slot_df.copy()

    slots_by_day = {}
    for d in DAYS:
        jams = kbm_slots[kbm_slots['Hari'].astype(str).str.strip().str.capitalize() == d]['Jam'].tolist()
        slots_by_day[d] = sorted(list(set(jams)))

    # Informasi Guru & MGMP
    guru_info = {}
    for _, r in guru_df.iterrows():
        g_id = str(r['ID Guru']).strip()
        status = str(r.get('Status', '')).strip().upper()
        mgmp_day = str(r.get('Hari_MGMP', '')).strip().capitalize() if 'Hari_MGMP' in r else None
        guru_info[g_id] = {
            'nama': r['Nama Guru'],
            'is_gtt': 'GTT' in status,
            'mgmp_day': mgmp_day
        }

    # Pembentukan Gugus Tugas Per Mapel
    assignment_groups = []
    for _, item in gm_df.iterrows():
        g_id = str(item['ID Guru']).strip()
        mapel = str(item['Mapel']).strip()
        m_lower = mapel.lower()
        kelas = item['Kelas']

        if 'indonesia' in m_lower or 'bin' in m_lower:
            blocks = [2, 2, 2]
            min_gap = 1
        elif 'ipa' in m_lower or 'ilmu pengetahuan alam' in m_lower:
            blocks = [2, 2, 1]
            min_gap = 1
        elif 'matematika' in m_lower or 'mtk' in m_lower:
            blocks = [2, 2, 1]
            min_gap = 1
        elif 'inggris' in m_lower or 'big' in m_lower:
            blocks = [2, 2]
            min_gap = 1
        elif 'ips' in m_lower or 'ilmu pengetahuan sosial' in m_lower:
            blocks = [2, 2]
            min_gap = 1
        elif any(k in m_lower for k in ['pancasila', 'pp', 'pkn']):
            blocks = [2, 1]
            min_gap = 1
        elif 'pjok' in m_lower or 'jasmani' in m_lower:
            blocks = [3]
            min_gap = 0
        elif 'agama' in m_lower or 'pai' in m_lower:
            blocks = [3]
            min_gap = 0
        elif 'jawa' in m_lower or 'bjw' in m_lower:
            blocks = [2]
            min_gap = 0
        else:
            blocks = [3]
            min_gap = 0

        assignment_groups.append({
            'guru_id': g_id,
            'nama_guru': guru_info.get(g_id, {}).get('nama', item['Nama Guru']),
            'mapel': mapel,
            'kelas': kelas,
            'blocks': blocks,
            'min_gap': min_gap,
            'workload': guru_workload.get(g_id, 1)
        })

    # PRIORITAS PLOTTING DINAMIS:
    # 0: PAI 7A (Terkunci)
    # 1: PJOK (Jam Pagi)
    # 2: PAI Kelas Lain
    # 3: Guru dengan Beban Mengajar Tinggi (Banyak Paralel Kelas)
    def priority_key(group):
        m = group['mapel'].lower()
        k = group['kelas']
        if ('agama' in m or 'pai' in m) and k == '7A': return (0, 0)
        if 'pjok' in m or 'jasmani' in m: return (1, 0)
        if 'agama' in m or 'pai' in m: return (2, 0)
        # Prioritaskan guru dengan kelas terbanyak (workload tinggi)
        return (3, -group['workload'])

    assignment_groups.sort(key=priority_key)

    schedule_board = {}
    unassigned = []

    for group in assignment_groups:
        g_id = group['guru_id']
        mapel = group['mapel']
        m_lower = mapel.lower()
        kelas = group['kelas']
        blocks = group['blocks']
        min_gap = group['min_gap']
        g_meta = guru_info.get(g_id, {'is_gtt': True, 'mgmp_day': None})

        scheduled_days_idx = []

        for b_size in blocks:
            block_placed = False

            # --- PAI KELAS 7A (LOCKED: KAMIS JAM 1-3) ---
            if ('agama' in m_lower or 'pai' in m_lower) and kelas == '7A':
                target_day = 'Kamis'
                target_jams = [1, 2, 3]
                bentrok = False

                for j in target_jams:
                    if (target_day, j) in schedule_board:
                        for e in schedule_board[(target_day, j)]:
                            if e['guru_id'] == g_id or e['kelas'] == kelas:
                                bentrok = True; break
                if not bentrok:
                    for j in target_jams:
                        schedule_board.setdefault((target_day, j), []).append({
                            'guru_id': g_id, 'nama_guru': group['nama_guru'],
                            'mapel': mapel, 'kelas': kelas
                        })
                    scheduled_days_idx.append(DAY_INDEX[target_day])
                    block_placed = True
                    continue

            # MULTI-PASS PLOTTING ENGINE (Pass 1: Ideal, Pass 2: Flex Gap, Pass 3: Emergency Split 1 JP)
            target_sizes = [b_size]
            if b_size == 2:
                # Jika 2 JP gagal di-plot utuh, boleh dicoba split jadi [1, 1]
                target_sizes = [2, 1, 1]

            for current_size in target_sizes:
                if block_placed and target_sizes == [b_size]: break

                sub_placed = False
                for pass_num in [1, 2]:
                    if sub_placed: break

                    for day in DAYS:
                        d_idx = DAY_INDEX[day]

                        # Pass 1: Cek jeda hari
                        if pass_num == 1 and scheduled_days_idx and min_gap > 0:
                            if any(abs(d_idx - past_idx) <= min_gap for past_idx in scheduled_days_idx):
                                continue

                        # Pass 2: Hindari menumpuk di hari yang sama jika belum terdesak
                        if pass_num == 2 and d_idx in scheduled_days_idx and current_size > 1:
                            continue

                        avail_jams = slots_by_day.get(day, [])

                        # PJOK ATURAN KHUSUS
                        if 'pjok' in m_lower or 'jasmani' in m_lower:
                            if day == 'Senin': target_jams = [2, 3, 4]
                            elif day in ['Selasa', 'Rabu', 'Kamis']: target_jams = [1, 2, 3]
                            else: continue

                            bentrok = False
                            for j in target_jams:
                                if j not in avail_jams or (day, j) in schedule_board:
                                    for e in schedule_board.get((day, j), []):
                                        if e['guru_id'] == g_id or e['kelas'] == kelas:
                                            bentrok = True; break
                            if not bentrok:
                                for j in target_jams:
                                    schedule_board.setdefault((day, j), []).append({
                                        'guru_id': g_id, 'nama_guru': group['nama_guru'],
                                        'mapel': mapel, 'kelas': kelas
                                    })
                                scheduled_days_idx.append(d_idx)
                                sub_placed = True
                                break
                            continue

                        # MGMP NON-GTT
                        valid_jams = list(avail_jams)
                        if not g_meta['is_gtt'] and g_meta['mgmp_day'] == day:
                            valid_jams = [j for j in avail_jams if j <= 3]

                        # BROWSE JAM
                        for jam in valid_jams:
                            if not all((jam + offset) in valid_jams for offset in range(current_size)):
                                continue

                            # Maksimal 5 Mapel Berbeda Per Hari Per Kelas
                            current_mapels_day = set()
                            for (d, j), entries in schedule_board.items():
                                if d == day:
                                    for e in entries:
                                        if e['kelas'] == kelas:
                                            current_mapels_day.add(e['mapel'])

                            if mapel not in current_mapels_day and len(current_mapels_day) >= 5:
                                continue

                            # Cek Bentrok Jam
                            bentrok = False
                            for offset in range(current_size):
                                slot_key = (day, jam + offset)
                                if slot_key in schedule_board:
                                    for e in schedule_board[slot_key]:
                                        if e['guru_id'] == g_id or e['kelas'] == kelas:
                                            bentrok = True; break
                                if bentrok: break

                            if not bentrok:
                                for offset in range(current_size):
                                    slot_key = (day, jam + offset)
                                    schedule_board.setdefault(slot_key, []).append({
                                        'guru_id': g_id, 'nama_guru': group['nama_guru'],
                                        'mapel': mapel, 'kelas': kelas
                                    })
                                scheduled_days_idx.append(d_idx)
                                sub_placed = True
                                break

                        if sub_placed: break

                if sub_placed and target_sizes == [b_size]:
                    block_placed = True
                    break

            if not sub_placed and not block_placed:
                unassigned.append({
                    'guru_id': g_id, 'nama_guru': group['nama_guru'],
                    'kelas': kelas, 'mapel': mapel, 'block_size': b_size
                })

    # Format ke DataFrame
    rows = []
    for (hari, jam), list_entries in schedule_board.items():
        for e in list_entries:
            nama_depan = clean_first_name(e['nama_guru'])
            m_str = e['mapel'].lower()
            mapel_singkat = MAPEL_SHORT.get(m_str, e['mapel'][:4].upper())
            kode_mapel = MAPEL_TO_KODE.get(m_str, 'MXX')

            rows.append({
                'Hari': hari, 'Jam': jam, 'Kelas': e['kelas'],
                'ID Guru': e['guru_id'], 'Nama Guru Full': e['nama_guru'],
                'Nama Guru': nama_depan, 'Mapel Full': e['mapel'],
                'Mapel Singkat': mapel_singkat, 'Kode Mapel': kode_mapel
            })

    df_res = pd.DataFrame(rows)
    if not df_res.empty:
        df_res['Hari'] = pd.Categorical(df_res['Hari'], categories=DAYS, ordered=True)
        df_res = df_res.sort_values(by=['Hari', 'Jam', 'Kelas']).reset_index(drop=True)

    return df_res, unassigned

# --- INISIALISASI SESSION STATE ---
if 'df_schedule' not in st.session_state:
    st.session_state['df_schedule'] = pd.DataFrame()
if 'unassigned' not in st.session_state:
    st.session_state['unassigned'] = []

# --- TOMBOL GENERATE ---
btn_generate = st.button("🚀 Generate Jadwal Kelas 7 Sekarang", type="primary")

if btn_generate:
    with st.spinner("Memproses plotting jadwal kelas 7A - 7E..."):
        try:
            df_sched, unassigned_list = generate_schedule_kelas_7(input_data)
            st.session_state['df_schedule'] = df_sched
            st.session_state['unassigned'] = unassigned_list
            st.rerun()
        except Exception as e:
            st.error(f"Terjadi kesalahan saat memproses data: {e}")
            st.stop()

df_schedule = st.session_state['df_schedule']
unassigned = st.session_state['unassigned']

# --- DISPLAY HASIL MATRIKS ---
if not df_schedule.empty:
    df_schedule['Display_Nama'] = df_schedule['Mapel Singkat'] + "\n(" + df_schedule['Nama Guru'] + ")"
    matrix_nama = df_schedule.pivot_table(
        index=['Hari', 'Jam'], columns='Kelas', values='Display_Nama', aggfunc='first'
    ).fillna('-')

    df_schedule['Display_Kode'] = df_schedule['Kode Mapel'] + " (" + df_schedule['ID Guru'] + ")"
    matrix_kode = df_schedule.pivot_table(
        index=['Hari', 'Jam'], columns='Kelas', values='Display_Kode', aggfunc='first'
    ).fillna('-')

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Slot Terisi", len(df_schedule))
    c2.metric("Jumlah Kelas", df_schedule['Kelas'].nunique())
    c3.metric("Jumlah Guru", df_schedule['ID Guru'].nunique())
    c4.metric("Jam Belum Muat", len(unassigned), delta_color="inverse")

    tab_nama, tab_kode, tab_detail, tab_unassigned = st.tabs([
        "👤 Matriks (Nama Guru)", "🔢 Matriks (Kode Mapel)", "📋 Master List", "⚠️ Belum Muat"
    ])

    with tab_nama:
        st.subheader("Matriks Jadwal Kelas 7A - 7E (Nama Guru)")
        st.dataframe(matrix_nama, use_container_width=True)

    with tab_kode:
        st.subheader("Matriks Jadwal Kelas 7A - 7E (Kode Mapel)")
        st.dataframe(matrix_kode, use_container_width=True)

    with tab_detail:
        st.dataframe(df_schedule, use_container_width=True)

    with tab_unassigned:
        if unassigned:
            st.warning(f"Ada {len(unassigned)} alokasi jam yang tidak muat.")
            st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
        else:
            st.success("🎉 Seluruh mata pelajaran kelas 7A-7E berhasil diplot 100%!")

    # --- DOWNLOAD EXCEL ---
    st.markdown("---")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        matrix_nama.to_excel(writer, sheet_name='Matriks_Nama_Guru')
        matrix_kode.to_excel(writer, sheet_name='Matriks_Kode_Mapel')
        df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
        if unassigned:
            pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)

    st.download_button(
        label="📥 Download Hasil Pemetaan ke Excel",
        data=buffer.getvalue(),
        file_name="Hasil_Pemetaan_Jadwal_Kelas7.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
