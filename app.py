import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="AI Schedule Generator", page_icon="🤖", layout="wide")

st.title("🤖 AI Automatic Schedule Generator")
st.write("Sistem Pembuat Jadwal Pelajaran Otomatis Bebas Bentrok dan Sesuai Aturan KBM.")

# --- SIDEBAR & FILE INPUT ---
st.sidebar.header("📁 Input Database")
uploaded_file = st.sidebar.file_uploader("Upload File Database Excel", type=["xlsx", "xls"])
target_file_path = st.sidebar.text_input("Atau ketik jalur file lokal:", value="database_scheduler.xlsx")

input_data = uploaded_file if uploaded_file is not None else target_file_path

def normalize_text(text):
    if pd.isna(text):
        return ""
    return re.sub(r'[^a-z0-9]', '', str(text).lower())

def clean_first_name(nama_full):
    if pd.isna(nama_full):
        return ""
    clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
    words = clean_str.split()
    return words[0] if words else ""

def get_slot_structure_by_mapel(mapel_raw, val_raw):
    norm = normalize_text(mapel_raw)
    
    # 1. Matematika & IPA -> 2, 2, 1
    if any(k in norm for k in ['matematika', 'mtk', 'm07', 'ipa', 'm08']):
        return [2, 2, 1]
    # 2. Bahasa Indonesia -> 2, 2, 2
    elif any(k in norm for k in ['indonesia', 'bin', 'm06']):
        return [2, 2, 2]
    # 3. IPS & Bahasa Inggris -> 2, 2
    elif any(k in norm for k in ['ips', 'm09', 'inggris', 'ing', 'big', 'm10']):
        return [2, 2]
    # 4. Pendidikan Pancasila -> 2, 1
    elif any(k in norm for k in ['pancasila', 'pp', 'pkn', 'm05']):
        return [2, 1]
    # 5. Lainnya -> 3
    else:
        if not pd.isna(val_raw):
            val_str = str(val_raw).strip()
            if ',' in val_str or ';' in val_str:
                res = [int(x.strip()) for x in val_str.replace(';', ',').split(',') if x.strip().isdigit()]
                if res:
                    return res
            elif val_str.isdigit():
                return [int(val_str)]
        return [3]

def get_mapel_info(mapel_raw):
    norm = normalize_text(mapel_raw)
    if any(k in norm for k in ['inggris', 'ing', 'big', 'm10']):
        return 'M10', 'BIG'
    elif any(k in norm for k in ['pancasila', 'pp', 'pkn', 'm05']):
        return 'M05', 'PP'
    elif any(k in norm for k in ['agama', 'islam', 'pai', 'm01']):
        return 'M01', 'PAI'
    elif any(k in norm for k in ['indonesia', 'bin', 'm06']):
        return 'M06', 'BIN'
    elif any(k in norm for k in ['matematika', 'mtk', 'm07']):
        return 'M07', 'MTK'
    elif any(k in norm for k in ['ipa', 'm08']):
        return 'M08', 'IPA'
    elif any(k in norm for k in ['ips', 'm09']):
        return 'M09', 'IPS'
    elif any(k in norm for k in ['jasmani', 'pjok', 'm11']):
        return 'M11', 'PJOK'
    elif any(k in norm for k in ['informatika', 'inf', 'm12']):
        return 'M12', 'INF'
    elif any(k in norm for k in ['seni', 'snb', 'm13']):
        return 'M13', 'SNB'
    elif any(k in norm for k in ['prakarya', 'prk', 'm14']):
        return 'M14', 'PRK'
    elif any(k in norm for k in ['jawa', 'bjw', 'm15']):
        return 'M15', 'BJW'
    elif any(k in norm for k in ['konseling', 'bk', 'm16']):
        return 'M16', 'BK'
    else:
        return 'MXX', str(mapel_raw).strip()[:4].upper()

def get_sheet_df(xls, target_name):
    target_clean = normalize_text(target_name)
    for sheet in xls.sheet_names:
        if target_clean in normalize_text(sheet):
            df = pd.read_excel(xls, sheet)
            df.columns = [str(c).strip() for c in df.columns]
            return df
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan!")

# --- ENGINE ALGORITMA SCHEDULE ---
def generate_schedule(excel_source):
    xls = pd.ExcelFile(excel_source)
    guru_df = get_sheet_df(xls, 'Guru')
    slot_df = get_sheet_df(xls, 'Slot')
    gm_df = get_sheet_df(xls, 'Guru_Mengajar')

    mgmp_days = {}
    guru_status = {}
    if 'ID Guru' in guru_df.columns:
        if 'Hari MGMP' in guru_df.columns:
            mgmp_days = dict(zip(guru_df['ID Guru'].astype(str).str.strip(), guru_df['Hari MGMP'].fillna('')))
        if 'Status' in guru_df.columns:
            guru_status = dict(zip(guru_df['ID Guru'].astype(str).str.strip(), guru_df['Status'].fillna('')))

    # CEK KOLOM SLOT
    slot_col = None
    for c in gm_df.columns:
        if any(kw in c.lower() for kw in ['slot', 'alokasi', 'jp', 'jam']):
            slot_col = c
            break
    if not slot_col:
        slot_col = gm_df.columns[-1]

    # FILTER SLOT KBM (Memastikan Jam ke-2 Senin tidak terlewatkan)
    slot_df['Jam'] = pd.to_numeric(slot_df['Jam'], errors='coerce')
    slot_df = slot_df.dropna(subset=['Jam'])
    slot_df['Jam'] = slot_df['Jam'].astype(int)

    jenis_col = [c for c in slot_df.columns if 'jenis' in c.lower() or 'keterangan' in c.lower()]
    if jenis_col:
        j_name = jenis_col[0]
        # Hanya buang yang bertuliskan Upacara/Istirahat/Sholat/Pembiasaan
        kbm_slots = slot_df[~slot_df[j_name].astype(str).str.upper().str.contains('ISTIRAHAT|UPACARA|PEMBIASAAN|SHOLAT')].copy()
    else:
        kbm_slots = slot_df.copy()

    days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    slots_by_day = {}
    for d in days:
        jams = kbm_slots[kbm_slots['Hari'].astype(str).str.strip().str.capitalize() == d]['Jam'].tolist()
        slots_by_day[d] = sorted(list(set(jams)))

    gm_df['Slot_List'] = gm_df.apply(lambda row: get_slot_structure_by_mapel(row['Mapel'], row[slot_col]), axis=1)
    gm_df['ID Guru'] = gm_df['ID Guru'].astype(str).str.strip()
    records = gm_df.to_dict(orient='records')

    # PRIORITAS B. INGGRIS & PJOK DILAYANI TERLEBIH DAHULU
    def get_priority(item):
        norm = normalize_text(item['Mapel'])
        if any(k in norm for k in ['inggris', 'ing', 'big', 'm10']):
            return 0
        elif any(k in norm for k in ['pjok', 'jasmani', 'm11']):
            return 1
        elif any(k in norm for k in ['matematika', 'mtk', 'm07']):
            return 2
        return 3

    records.sort(key=get_priority)

    schedule_board = {}
    unassigned = []

    for item in records:
        guru_id = str(item['ID Guru']).strip()
        guru_nama = item['Nama Guru']
        mapel = item['Mapel']
        kelas = item['Kelas']
        slot_blocks = item.get('Slot_List', [])
        norm_mapel = normalize_text(mapel)

        is_inggris = any(k in norm_mapel for k in ['inggris', 'ing', 'big', 'm10'])
        is_pjok = any(k in norm_mapel for k in ['pjok', 'jasmani', 'm11'])
        is_mtk = any(k in norm_mapel for k in ['matematika', 'mtk', 'm07'])

        status_g = str(guru_status.get(guru_id, '')).strip().upper()
        is_gtt = 'GTT' in status_g
        mgmp_day = str(mgmp_days.get(guru_id, '')).strip()

        days_assigned = set()

        for block_size in slot_blocks:
            placed = False

            search_days = ['Jumat', 'Senin', 'Rabu', 'Kamis', 'Selasa'] if is_inggris else days

            for mode in ['strict', 'moderate', 'flexible', 'emergency']:
                if placed:
                    break

                for day in search_days:
                    if placed:
                        break

                    if day in days_assigned and mode not in ['flexible', 'emergency']:
                        continue

                    is_mgmp_today = (mgmp_day.lower() == day.lower()) or (is_inggris and day.lower() == 'selasa')

                    if is_mgmp_today and mode not in ['flexible', 'emergency']:
                        if is_gtt or is_inggris:
                            continue

                    available_jams = slots_by_day.get(day, [])

                    for jam in available_jams:
                        if is_pjok and mode in ['strict', 'moderate'] and jam != 1:
                            continue
                        if is_mtk and block_size == 2 and mode in ['strict', 'moderate'] and jam > 2:
                            continue

                        if is_mgmp_today and not is_gtt and mode not in ['flexible', 'emergency']:
                            if (jam + block_size - 1) > 3:
                                continue

                        if not all((jam + offset) in available_jams for offset in range(block_size)):
                            continue

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
                            days_assigned.add(day)
                            break

            if not placed:
                unassigned.append({
                    'guru_id': guru_id,
                    'nama_guru': guru_nama,
                    'kelas': kelas,
                    'mapel': mapel,
                    'block_size': block_size
                })

    # OUTPUT DATA
    rows = []
    for (hari, jam), assignments in schedule_board.items():
        for item in assignments:
            nama_depan = clean_first_name(item['nama_guru'])
            kode_mapel, mapel_singkat = get_mapel_info(item['mapel'])

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

    return pd.DataFrame(rows), unassigned

# --- UI STREAMLIT ---
btn_generate = st.button("🚀 Generate Jadwal Sekarang", type="primary")

if btn_generate or 'df_schedule' not in st.session_state:
    with st.spinner("Mengolah jadwal..."):
        try:
            df_sched, unassigned_list = generate_schedule(input_data)
            st.session_state['df_schedule'] = df_sched
            st.session_state['unassigned'] = unassigned_list
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

df_schedule = st.session_state['df_schedule']
unassigned = st.session_state['unassigned']

if not df_schedule.empty:
    df_schedule['Display_Nama'] = df_schedule['Mapel Singkat'] + "\n(" + df_schedule['Nama Guru'] + ")"
    matrix_nama = df_schedule.pivot_table(
        index=['Hari', 'Jam'], columns='Kelas', values='Display_Nama', aggfunc='first'
    ).fillna('-')

    df_schedule['Display_Kode'] = df_schedule['Kode Mapel'] + " (" + df_schedule['ID Guru'] + ")"
    matrix_kode = df_schedule.pivot_table(
        index=['Hari', 'Jam'], columns='Kelas', values='Display_Kode', aggfunc='first'
    ).fillna('-')
else:
    matrix_nama, matrix_kode = pd.DataFrame(), pd.DataFrame()

# METRIK DASHBOARD
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Slot Terisi", len(df_schedule))
m2.metric("Jumlah Kelas", df_schedule['Kelas'].nunique() if not df_schedule.empty else 0)
m3.metric("Jumlah Guru", df_schedule['ID Guru'].nunique() if not df_schedule.empty else 0)
m4.metric("Gagal (Unassigned)", len(unassigned), delta_color="inverse")

# TAB DISPLAY
t1, t2, t3, t4 = st.tabs(["👤 Matriks (Nama)", "🔢 Matriks (Kode)", "📋 Master Detail", "⚠️ Unassigned"])

with t1:
    st.dataframe(matrix_nama, use_container_width=True)
with t2:
    st.dataframe(matrix_kode, use_container_width=True)
with t3:
    st.dataframe(df_schedule, use_container_width=True)
with t4:
    if unassigned:
        st.warning(f"Terdapat {len(unassigned)} item belum terjadwal:")
        st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
    else:
        st.success("🎉 Berhasil! Jam ke-2 Senin beserta seluruh jam KBM terisi dengan sempurna!")

# DOWNLOAD EXCEL
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    matrix_nama.to_excel(writer, sheet_name='Matriks_Nama')
    matrix_kode.to_excel(writer, sheet_name='Matriks_Kode')
    df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
    if unassigned:
        pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)

st.download_button(
    label="📥 Download Excel Hasil Jadwal",
    data=buffer.getvalue(),
    file_name="Jadwal_Pelajaran_Terbaru.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
