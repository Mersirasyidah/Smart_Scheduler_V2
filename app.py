import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Generator Jadwal Kelas 7", page_icon="🏫", layout="wide")

st.title("🏫 AI Automatic Schedule Generator — Kelas 7 (7A - 7E)")
st.write("Sistem Plotting Jadwal Khusus Jenjang Kelas 7 berdasarkan Prioritas & Aturan Khusus.")

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
    'pendidikan agama islam': 'M01', 'pai': 'M01',
    'bimbingan konseling': 'M16', 'bk': 'M16'
}

MAPEL_SHORT = {
    'pjok': 'PJOK', 'matematika': 'MTK', 'ilmu pengetahuan alam': 'IPA',
    'ilmu pengetahuan sosial': 'IPS', 'informatika': 'INF', 'prakarya': 'PRK',
    'seni budaya': 'SNB', 'pendidikan pancasila': 'PP', 'bahasa jawa': 'BJW',
    'bahasa indonesia': 'BIN', 'bahasa inggris': 'BIG', 'pendidikan agama islam': 'PAI'
}

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

    days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    slots_by_day = {}
    for d in days:
        jams = kbm_slots[kbm_slots['Hari'].astype(str).str.strip().str.capitalize() == d]['Jam'].tolist()
        slots_by_day[d] = sorted(list(set(jams)))

    # Informasi Guru & MGMP
    guru_info = {}
    for _, r in guru_df.iterrows():
        g_id = str(r['ID Guru']).strip()
        status = str(r.get('Status', '')).strip().upper()  # PNS, PPPK, GTT
        mgmp_day = str(r.get('Hari_MGMP', '')).strip().capitalize() if 'Hari_MGMP' in r else None
        guru_info[g_id] = {
            'nama': r['Nama Guru'],
            'is_gtt': 'GTT' in status,
            'mgmp_day': mgmp_day
        }

    # Pembentukan Blok Penugasan Sesuai Aturan
    assignments = []
    for _, item in gm_df.iterrows():
        g_id = str(item['ID Guru']).strip()
        mapel = str(item['Mapel']).strip()
        m_lower = mapel.lower()
        kelas = item['Kelas']

        # Tentukan skema pembagian JP berdasarkan aturan
        if 'pjok' in m_lower or 'jasmani' in m_lower:
            blocks = [3]  # 3 JP
        elif 'matematika' in m_lower or 'mtk' in m_lower:
            blocks = [2, 2, 1]  # 5 JP -> 2, 2, 1
        elif 'ipa' in m_lower or 'ilmu pengetahuan alam' in m_lower:
            blocks = [2, 2, 1]  # 5 JP -> 2, 2, 1
        elif 'ips' in m_lower or 'ilmu pengetahuan sosial' in m_lower:
            blocks = [2, 2]     # 4 JP -> 2, 2
        elif any(k in m_lower for k in ['informatika', 'prakarya', 'seni', 'pancasila', 'pp', 'pkn']):
            blocks = [3]        # Mapel 3 JP
        elif 'jawa' in m_lower or 'bjw' in m_lower:
            blocks = [2]        # Bahasa Jawa 2 JP
        else:
            blocks = [2, 2]     # Default mapel umum lainnya

        for b in blocks:
            assignments.append({
                'guru_id': g_id,
                'nama_guru': guru_info.get(g_id, {}).get('nama', item['Nama Guru']),
                'mapel': mapel,
                'kelas': kelas,
                'block_size': b
            })

    # PRIORITAS PLOTTING: PJOK -> MTK -> IPA -> Lainnya
    def priority_key(item):
        m = item['mapel'].lower()
        if 'pjok' in m or 'jasmani' in m: return 1
        if 'matematika' in m or 'mtk' in m: return 2
        if 'ipa' in m or 'ilmu pengetahuan alam' in m: return 3
        return 4

    assignments.sort(key=priority_key)

    schedule_board = {}
    unassigned = []

    for item in assignments:
        g_id = item['guru_id']
        m_lower = item['mapel'].lower()
        kelas = item['kelas']
        b_size = item['block_size']
        g_meta = guru_info.get(g_id, {'is_gtt': True, 'mgmp_day': None})

        placed = False

        for day in days:
            if placed: break
            avail_jams = slots_by_day.get(day, [])

            # --- ATURAN 1: PJOK (Senin: Jam 2-4, Selasa-Kamis: Jam 1-3) ---
            if 'pjok' in m_lower or 'jasmani' in m_lower:
                if day == 'Senin':
                    target_jams = [2, 3, 4]
                elif day in ['Selasa', 'Rabu', 'Kamis']:
                    target_jams = [1, 2, 3]
                else:
                    continue  # Tidak diplot di luar aturan hari PJOK

                # Cek ketersediaan slot & bentrok
                bentrok = False
                for j in target_jams:
                    if j not in avail_jams or (day, j) in schedule_board:
                        for e in schedule_board.get((day, j), []):
                            if e['guru_id'] == g_id or e['kelas'] == kelas:
                                bentrok = True; break
                if not bentrok:
                    for j in target_jams:
                        schedule_board.setdefault((day, j), []).append({
                            'guru_id': g_id, 'nama_guru': item['nama_guru'],
                            'mapel': item['mapel'], 'kelas': kelas
                        })
                    placed = True
                    break
                continue

            # --- ATURAN 8: BANTUAN HARI MGMP GURU NON-GTT ---
            valid_jams_for_day = list(avail_jams)
            if not g_meta['is_gtt'] and g_meta['mgmp_day'] == day:
                # Batasi hanya Jam 1 - 3
                valid_jams_for_day = [j for j in avail_jams if j <= 3]

            # --- BROWSE JAM UNTUK MAPEL LAINNYA ---
            for jam in valid_jams_for_day:
                # Pastikan blok muat secara berturut-turut
                if not all((jam + offset) in valid_jams_for_day for offset in range(b_size)):
                    continue

                # --- ATURAN 5: Maksimal 5 Mapel Berbeda Per Hari Per Kelas ---
                current_mapels_day = set()
                for (d, j), entries in schedule_board.items():
                    if d == day:
                        for e in entries:
                            if e['kelas'] == kelas:
                                current_mapels_day.add(e['mapel'])

                if item['mapel'] not in current_mapels_day and len(current_mapels_day) >= 5:
                    continue  # Melebihi kuota 5 mapel/hari

                # Cek bentrok guru atau kelas
                bentrok = False
                for offset in range(b_size):
                    slot_key = (day, jam + offset)
                    if slot_key in schedule_board:
                        for e in schedule_board[slot_key]:
                            if e['guru_id'] == g_id or e['kelas'] == kelas:
                                bentrok = True; break
                    if bentrok: break

                if not bentrok:
                    for offset in range(b_size):
                        slot_key = (day, jam + offset)
                        schedule_board.setdefault(slot_key, []).append({
                            'guru_id': g_id, 'nama_guru': item['nama_guru'],
                            'mapel': item['mapel'], 'kelas': kelas
                        })
                    placed = True
                    break

        if not placed:
            unassigned.append({
                'guru_id': g_id, 'nama_guru': item['nama_guru'],
                'kelas': kelas, 'mapel': item['mapel'], 'block_size': b_size
            })

    # Konversi hasil ke DataFrame
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

    return pd.DataFrame(rows), unassigned

# --- INISIALISASI SESSION STATE ---
if 'df_schedule' not in st.session_state:
    st.session_state['df_schedule'] = pd.DataFrame()
if 'unassigned' not in st.session_state:
    st.session_state['unassigned'] = []

# --- TOMBOL GENERATE ---
btn_generate = st.button("🚀 Generate Jadwal Kelas 7 Sekarang", type="primary")

if btn_generate:
    with st.spinner("Memproses plotting jadwal kelas 7A - 7E berdasarkan aturan khusus..."):
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
