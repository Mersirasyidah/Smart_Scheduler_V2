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

def parse_slot_list(val):
    if pd.isna(val):
        return [1]
    res = [int(x.strip()) for x in str(val).replace(';', ',').split(',') if str(x).strip().isdigit()]
    return res if res else [1]

def get_mapel_info(mapel_raw):
    norm = normalize_text(mapel_raw)
    if 'inggris' in norm or 'big' in norm or 'm10' in norm:
        return 'M10', 'BIG'
    elif 'pancasila' in norm or 'pp' in norm or 'pkn' in norm or 'm05' in norm:
        return 'M05', 'PP'
    elif 'agama' in norm or 'islam' in norm or 'pai' in norm or 'm01' in norm:
        return 'M01', 'PAI'
    elif 'indonesia' in norm or 'bin' in norm or 'm06' in norm:
        return 'M06', 'BIN'
    elif 'matematika' in norm or 'mtk' in norm or 'm07' in norm:
        return 'M07', 'MTK'
    elif 'ipa' in norm or 'm08' in norm:
        return 'M08', 'IPA'
    elif 'ips' in norm or 'm09' in norm:
        return 'M09', 'IPS'
    elif 'jasmani' in norm or 'pjok' in norm or 'm11' in norm:
        return 'M11', 'PJOK'
    elif 'informatika' in norm or 'inf' in norm or 'm12' in norm:
        return 'M12', 'INF'
    elif 'seni' in norm or 'snb' in norm or 'm13' in norm:
        return 'M13', 'SNB'
    elif 'prakarya' in norm or 'prk' in norm or 'm14' in norm:
        return 'M14', 'PRK'
    elif 'jawa' in norm or 'bjw' in norm or 'm15' in norm:
        return 'M15', 'BJW'
    elif 'konseling' in norm or 'bk' in norm or 'm16' in norm:
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

    slot_col = 'Slot'
    for c in gm_df.columns:
        if 'slot' in c.lower() or 'alokasi' in c.lower():
            slot_col = c
            break

    # FILTER SLOT KBM
    jenis_col = [c for c in slot_df.columns if 'jenis' in c.lower() or 'keterangan' in c.lower()]
    if jenis_col:
        j_name = jenis_col[0]
        kbm_slots = slot_df[~slot_df[j_name].astype(str).str.upper().str.contains('ISTIRAHAT|UPACARA|PEMBIASAAN|SHOLAT')].dropna(subset=['Jam']).copy()
    else:
        kbm_slots = slot_df.dropna(subset=['Jam']).copy()

    kbm_slots['Jam'] = kbm_slots['Jam'].astype(int)
    days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    slots_by_day = {d: kbm_slots[kbm_slots['Hari'] == d]['Jam'].tolist() for d in days}

    gm_df['Slot_List'] = gm_df[slot_col].apply(parse_slot_list)
    gm_df['ID Guru'] = gm_df['ID Guru'].astype(str).str.strip()
    records = gm_df.to_dict(orient='records')

    # PRIORITAS B. INGGRIS
    def get_priority(item):
        norm_mapel = normalize_text(item['Mapel'])
        is_inggris = 'inggris' in norm_mapel or 'big' in norm_mapel or 'm10' in norm_mapel
        return 0 if is_inggris else 1

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
        is_inggris = 'inggris' in norm_mapel or 'big' in norm_mapel or 'm10' in norm_mapel

        status_g = str(guru_status.get(guru_id, '')).strip().upper()
        is_gtt = 'GTT' in status_g
        mgmp_day = str(mgmp_days.get(guru_id, '')).strip()

        for block_size in slot_blocks:
            placed = False
            
            # Prioritas pencarian hari untuk Bahasa Inggris
            search_days = ['Jumat', 'Senin', 'Rabu', 'Kamis', 'Selasa'] if is_inggris else days

            for mode in ['strict', 'moderate', 'emergency']:
                if placed:
                    break

                for day in search_days:
                    if placed:
                        break

                    is_mgmp_today = (mgmp_day.lower() == day.lower())

                    # ATURAN MGMP DENGAN PERTIMBANGAN STATUS GURU:
                    # 1. Jika Guru GTT -> Dilarang mengajar full seharian di hari MGMP.
                    # 2. Jika Guru Non-GTT -> Dilarang mengajar jika jam mengajar > jam ke-3.
                    if is_mgmp_today and mode != 'emergency':
                        if is_gtt:
                            continue

                    available_jams = slots_by_day.get(day, [])
                    
                    for jam in available_jams:
                        # ATURAN KHUSUS NON-GTT DI HARI MGMP: Hanya boleh Jam 1, 2, atau 3
                        if is_mgmp_today and not is_gtt:
                            if (jam + block_size - 1) > 3:
                                continue

                        if not all((jam + offset) in available_jams for offset in range(block_size)):
                            continue

                        # Cek Bentrok Guru atau Kelas
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
        st.success("🎉 Berhasil! Seluruh jadwal terplot secara optimal sesuai status Guru & MGMP.")

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
