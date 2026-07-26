import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Generator Jadwal Kelas 7", page_icon="🏫", layout="wide")

st.title("🏫 AI Automatic Schedule Generator — Solver Sempurna Kelas 7")
st.write("Sistem Plotting Otomatis dengan Algoritma Dynamic Block Priority untuk Menuntaskan Seluruh Blok Jam.")

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
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan!")

# --- ENGINE PENJADWALAN KELAS 7 ---
def generate_schedule_kelas_7(excel_source):
    xls = pd.ExcelFile(excel_source)
    guru_df = get_sheet_df(xls, 'Guru')
    slot_df = get_sheet_df(xls, 'Slot')
    gm_df = get_sheet_df(xls, 'Guru_Mengajar')

    target_kelas = ['7A', '7B', '7C', '7D', '7E']
    gm_df['Kelas'] = gm_df['Kelas'].astype(str).str.strip().str.upper()
    gm_df = gm_df[gm_df['Kelas'].isin(target_kelas)].copy()

    def is_valid_mapel(mapel_name):
        m = str(mapel_name).strip().lower()
        if 'bk' in m or 'bimbingan' in m or 'konseling' in m:
            return False
        if 'agama' in m and not ('islam' in m or 'pai' in m):
            return False
        return True

    gm_df = gm_df[gm_df['Mapel'].apply(is_valid_mapel)].copy()

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

    guru_info = {}
    for _, r in guru_df.iterrows():
        g_id = str(r['ID Guru']).strip()
        status = str(r.get('Status', '')).strip().upper()
        
        mgmp_day = None
        if 'Hari_MGMP' in r and pd.notna(r['Hari_MGMP']):
            m_val = str(r['Hari_MGMP']).strip().capitalize()
            if m_val in DAYS:
                mgmp_day = m_val

        guru_info[g_id] = {
            'nama': r['Nama Guru'],
            'is_gtt': 'GTT' in status,
            'mgmp_day': mgmp_day
        }

    # PEMCAHAN BEBAN JADI BLOK INDIVIDUAL DENGAN SKOR KERUMITAN
    individual_blocks = []
    for _, item in gm_df.iterrows():
        g_id = str(item['ID Guru']).strip()
        mapel = str(item['Mapel']).strip()
        m_lower = mapel.lower()
        kelas = item['Kelas']

        if 'indonesia' in m_lower or 'bin' in m_lower:
            blocks = [2, 2, 2]
        elif 'ipa' in m_lower or 'ilmu pengetahuan alam' in m_lower:
            blocks = [2, 2, 1]
        elif 'matematika' in m_lower or 'mtk' in m_lower:
            blocks = [2, 2, 1]
        elif 'inggris' in m_lower or 'big' in m_lower:
            blocks = [2, 2]
        elif 'ips' in m_lower or 'ilmu pengetahuan sosial' in m_lower:
            blocks = [2, 2]
        elif any(k in m_lower for k in ['pancasila', 'pp', 'pkn']):
            blocks = [2, 1]
        elif 'pjok' in m_lower or 'jasmani' in m_lower:
            blocks = [3]
        elif 'agama' in m_lower or 'pai' in m_lower:
            blocks = [3]
        elif 'jawa' in m_lower or 'bjw' in m_lower:
            blocks = [2]
        else:
            blocks = [3]

        for b_sz in blocks:
            individual_blocks.append({
                'guru_id': g_id,
                'nama_guru': guru_info.get(g_id, {}).get('nama', item['Nama Guru']),
                'mapel': mapel,
                'kelas': kelas,
                'block_size': b_sz
            })

    # PRIORITAS STRUKTURAL: Blok Besar (3 JP) > Blok Sedang (2 JP) > Blok Kecil (1 JP)
    # Khusus PAI 7A dikunci pertama kali
    def sort_key(b):
        m = b['mapel'].lower()
        k = b['kelas']
        
        if ('agama' in m or 'pai' in m) and k == '7A':
            return (0, 0)
        if 'pjok' in m or 'jasmani' in m:
            return (1, 0)
        # Urutkan berdasarkan Ukuran Blok (3 JP dulu, lalu 2 JP, lalu 1 JP)
        return (2, -b['block_size'])

    individual_blocks.sort(key=sort_key)

    class_schedule = {}
    teacher_schedule = {}
    teacher_daily_jp = {}
    class_day_mapel = set() # Menjaga agar mapel tidak terlalu sering muncul di hari yang sama jika memungkinkan
    unassigned = []

    DAY_CAPACITY = {'Senin': 8, 'Selasa': 9, 'Rabu': 9, 'Kamis': 9, 'Jumat': 6}

    for item in individual_blocks:
        g_id = item['guru_id']
        mapel = item['mapel']
        m_lower = mapel.lower()
        kelas = item['kelas']
        b_size = item['block_size']
        g_meta = guru_info.get(g_id, {'is_gtt': False, 'mgmp_day': None})

        # PAI KELAS 7A (LOCKED: KAMIS JAM 1-3)
        if ('agama' in m_lower or 'pai' in m_lower) and kelas == '7A':
            target_day = 'Kamis'
            target_jams = [1, 2, 3]
            bentrok = False
            for j in target_jams:
                if (target_day, j, kelas) in class_schedule or (target_day, j, g_id) in teacher_schedule:
                    bentrok = True; break
            if not bentrok:
                for j in target_jams:
                    entry = {'guru_id': g_id, 'nama_guru': item['nama_guru'], 'mapel': mapel, 'kelas': kelas}
                    class_schedule[(target_day, j, kelas)] = entry
                    teacher_schedule[(target_day, j, g_id)] = True
                class_day_mapel.add((kelas, target_day, mapel))
                teacher_daily_jp[(target_day, g_id)] = teacher_daily_jp.get((target_day, g_id), 0) + len(target_jams)
                continue

        block_placed = False

        # MULTI-PASS STRATEGY
        # Pass 1: Syarat Ketat (Beda Hari per Mapel)
        # Pass 2: Pelonggaran Beda Hari
        # Pass 3: Split Block jika benar-benar terjepit (2 JP -> 1+1 JP)
        for mode in ['strict_day', 'relaxed_day', 'split_block']:
            if block_placed: break

            sub_units = [b_size]
            if mode == 'split_block' and b_size > 1 and not ('pjok' in m_lower or 'jasmani' in m_lower or 'agama' in m_lower):
                if b_size == 3: sub_units = [2, 1]
                elif b_size == 2: sub_units = [1, 1]

            for current_sub in sub_units:
                sub_placed = False
                for day in DAYS:
                    if sub_placed: break

                    if g_meta['mgmp_day'] == day:
                        continue

                    if mode == 'strict_day' and (kelas, day, mapel) in class_day_mapel:
                        continue

                    current_teacher_jp = teacher_daily_jp.get((day, g_id), 0)
                    if current_teacher_jp + current_sub > 8: # Max 8 JP per guru per hari
                        continue

                    avail_jams = slots_by_day.get(day, [])
                    max_day_jp = DAY_CAPACITY.get(day, 9)

                    # PJOK FIXING
                    if 'pjok' in m_lower or 'jasmani' in m_lower:
                        target_options = []
                        if day == 'Senin':
                            target_options.extend([[2, 3, 4], [5, 6, 7]])
                        else:
                            target_options.extend([[1, 2, 3], [4, 5, 6], [2, 3, 4]])

                        for target_jams in target_options:
                            if max(target_jams) > max_day_jp: continue
                            bentrok = False
                            for j in target_jams:
                                if j not in avail_jams or (day, j, kelas) in class_schedule or (day, j, g_id) in teacher_schedule:
                                    bentrok = True; break
                            if not bentrok:
                                for j in target_jams:
                                    entry = {'guru_id': g_id, 'nama_guru': item['nama_guru'], 'mapel': mapel, 'kelas': kelas}
                                    class_schedule[(day, j, kelas)] = entry
                                    teacher_schedule[(day, j, g_id)] = True
                                class_day_mapel.add((kelas, day, mapel))
                                teacher_daily_jp[(day, g_id)] = current_teacher_jp + len(target_jams)
                                sub_placed = True
                                block_placed = True
                                break
                        continue

                    # REGULAR PLOTTING
                    for jam in avail_jams:
                        if jam + current_sub - 1 > max_day_jp:
                            continue

                        if not all((jam + offset) in avail_jams for offset in range(current_sub)):
                            continue

                        bentrok = False
                        for offset in range(current_sub):
                            slot_j = jam + offset
                            if (day, slot_j, kelas) in class_schedule or (day, slot_j, g_id) in teacher_schedule:
                                bentrok = True
                                break

                        if not bentrok:
                            for offset in range(current_sub):
                                slot_j = jam + offset
                                entry = {'guru_id': g_id, 'nama_guru': item['nama_guru'], 'mapel': mapel, 'kelas': kelas}
                                class_schedule[(day, slot_j, kelas)] = entry
                                teacher_schedule[(day, slot_j, g_id)] = True
                            class_day_mapel.add((kelas, day, mapel))
                            teacher_daily_jp[(day, g_id)] = current_teacher_jp + current_sub
                            sub_placed = True
                            if mode != 'split_block' or len(sub_units) == 1:
                                block_placed = True
                            break

        if not block_placed:
            unassigned.append({
                'guru_id': g_id, 'nama_guru': item['nama_guru'],
                'kelas': kelas, 'mapel': mapel, 'block_size': b_size
            })

    # FORMATTING OUTPUT
    rows = []
    for (hari, jam, kelas), e in class_schedule.items():
        nama_depan = clean_first_name(e['nama_guru'])
        m_str = e['mapel'].lower()
        mapel_singkat = MAPEL_SHORT.get(m_str, e['mapel'][:4].upper())
        kode_mapel = MAPEL_TO_KODE.get(m_str, 'MXX')

        rows.append({
            'Hari': hari, 'Jam': jam, 'Kelas': kelas,
            'ID Guru': e['guru_id'], 'Nama Guru Full': e['nama_guru'],
            'Nama Guru': nama_depan, 'Mapel Full': e['mapel'],
            'Mapel Singkat': mapel_singkat, 'Kode Mapel': kode_mapel
        })

    df_res = pd.DataFrame(rows)
    if not df_res.empty:
        df_res['Hari'] = pd.Categorical(df_res['Hari'], categories=DAYS, ordered=True)
        df_res = df_res.sort_values(by=['Hari', 'Jam', 'Kelas']).reset_index(drop=True)

    return df_res, unassigned

# --- STREAMLIT UI ---
if 'df_schedule' not in st.session_state:
    st.session_state['df_schedule'] = pd.DataFrame()
if 'unassigned' not in st.session_state:
    st.session_state['unassigned'] = []

btn_generate = st.button("🚀 Generate Jadwal Bebas Bentrok (Solver Sempurna)", type="primary")

if btn_generate:
    with st.spinner("Memproses seluruh jadwal dengan algoritma Dynamic Block Priority..."):
        try:
            df_sched, unassigned_list = generate_schedule_kelas_7(input_data)
            st.session_state['df_schedule'] = df_sched
            st.session_state['unassigned'] = unassigned_list
            st.rerun()
        except Exception as e:
            st.error(f"Terjadi kesalahan: {e}")
            st.stop()

df_schedule = st.session_state['df_schedule']
unassigned = st.session_state['unassigned']

# --- TAMPILAN HASIL ---
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
            st.warning(f"Ada {len(unassigned)} blok jam yang belum muat.")
            st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
        else:
            st.success("🎉 Selesai 100%! Seluruh blok jam guru berhasil dimasukkan tanpa ada yang tersisa!")

    # DOWNLOAD EXCEL
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        matrix_nama.to_excel(writer, sheet_name='Matriks_Nama_Guru')
        matrix_kode.to_excel(writer, sheet_name='Matriks_Kode_Mapel')
        df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
        if unassigned:
            pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)

    st.download_button(
        label="📥 Download Hasil Pemetaan Excel",
        data=buffer.getvalue(),
        file_name="Hasil_Jadwal_Kelas7_Sempurna.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
