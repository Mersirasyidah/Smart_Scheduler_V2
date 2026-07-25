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

# --- FUNGSI MAPPING MAPEL (DENGAN DUKUNGAN 'Bahasa Inggris') ---
def normalize_text(text):
    if pd.isna(text):
        return ""
    # Hapus spasi ganda, tanda baca, dan ubah ke huruf kecil
    return re.sub(r'[^a-z0-9]', '', str(text).lower())

def clean_first_name(nama_full):
    if pd.isna(nama_full):
        return ""
    clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
    words = clean_str.split()
    return words[0] if words else ""

def parse_slot_list(val):
    if pd.isna(val):
        return []
    # Mengambil semua angka slot dari format seperti "2,2" atau "2, 1"
    return [int(x.strip()) for x in str(val).replace(';', ',').split(',') if str(x).strip().isdigit()]

def get_mapel_info(mapel_raw):
    norm = normalize_text(mapel_raw)
    
    # Deteksi Bahasa Inggris (Termasuk 'bahasainggris', 'b inggris', 'big', 'm10')
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
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan di file Excel!")

# --- ENGINE ALGORITMA PENYUSUNAN JADWAL ---
def generate_schedule(excel_source):
    xls = pd.ExcelFile(excel_source)
    guru_df = get_sheet_df(xls, 'Guru')
    slot_df = get_sheet_df(xls, 'Slot')
    gm_df = get_sheet_df(xls, 'Guru_Mengajar')

    mgmp_days = {}
    guru_status = {}
    if 'ID Guru' in guru_df.columns:
        if 'Hari MGMP' in guru_df.columns:
            mgmp_days = dict(zip(guru_df['ID Guru'], guru_df['Hari MGMP'].fillna('')))
        if 'Status' in guru_df.columns:
            guru_status = dict(zip(guru_df['ID Guru'], guru_df['Status'].fillna('')))

    slot_col = 'Slot'
    for c in gm_df.columns:
        if 'slot' in c.lower() or 'alokasi' in c.lower():
            slot_col = c
            break

    valid_types = ['PEMBELAJARAN', 'KBM']
    kbm_slots = slot_df[slot_df['Jenis'].astype(str).str.strip().str.upper().isin(valid_types)].dropna(subset=['Jam']).copy()
    kbm_slots['Jam'] = kbm_slots['Jam'].astype(int)

    days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    slots_by_day = {d: kbm_slots[kbm_slots['Hari'] == d]['Jam'].tolist() for d in days}

    gm_df['Slot_List'] = gm_df[slot_col].apply(parse_slot_list)
    records = gm_df.to_dict(orient='records')

    # B. INGGRIS DIPRIORITASKAN DI URUTAN PERTAMA
    def get_priority(item):
        norm_mapel = normalize_text(item['Mapel'])
        kelas = str(item['Kelas'])
        is_inggris = 'inggris' in norm_mapel or 'big' in norm_mapel or 'm10' in norm_mapel
        is_pjok = 'jasmani' in norm_mapel or 'pjok' in norm_mapel or 'm11' in norm_mapel
        is_mtk_ipa = 'matematika' in norm_mapel or 'mtk' in norm_mapel or 'ipa' in norm_mapel
        is_kelas_9 = kelas.startswith('9')

        if is_inggris:
            return (0, -item.get('JP', 0))  # Priority 0 (Paling Utama)
        elif is_pjok and is_kelas_9:
            return (1, -item.get('JP', 0))
        elif is_mtk_ipa and is_kelas_9:
            return (2, -item.get('JP', 0))
        elif is_pjok:
            return (3, -item.get('JP', 0))
        else:
            return (4, -item.get('JP', 0))

    records.sort(key=get_priority)

    schedule_board = {}
    unassigned = []

    # FASA 1: PLOTTING UTAMA
    for item in records:
        guru_id = item['ID Guru']
        guru_nama = item['Nama Guru']
        mapel = item['Mapel']
        kelas = item['Kelas']
        slot_blocks = item.get('Slot_List', [])

        norm_mapel = normalize_text(mapel)
        is_pjok = 'jasmani' in norm_mapel or 'pjok' in norm_mapel
        is_mtk_ipa = 'matematika' in norm_mapel or 'mtk' in norm_mapel or 'ipa' in norm_mapel

        for block_size in slot_blocks:
            placed = False
            
            # Melalui 3 Tingkat Kelonggaran Mode (Strict -> Moderate -> Emergency)
            for mode in ['strict', 'moderate', 'emergency']:
                if placed:
                    break

                for day in days:
                    if placed:
                        break

                    # Aturan pisah hari (diabaikan pada mode Emergency)
                    if mode != 'emergency':
                        already_placed = False
                        for (h, _), entries in schedule_board.items():
                            if h == day:
                                for e in entries:
                                    if e['kelas'] == kelas and normalize_text(e['mapel']) == norm_mapel:
                                        already_placed = True
                                        break
                            if already_placed:
                                break
                        if already_placed:
                            continue

                    mgmp_day = str(mgmp_days.get(guru_id, '')).strip().lower()
                    status = str(guru_status.get(guru_id, '')).strip().upper()
                    is_mgmp_day = (mgmp_day == day.lower())

                    if is_mgmp_day and status == 'GTT' and mode == 'strict':
                        continue

                    available_jams = slots_by_day.get(day, [])
                    
                    for jam in available_jams:
                        if is_mgmp_day and status != 'GTT' and mode == 'strict' and (jam + block_size - 1) > 3:
                            continue

                        if not all((jam + offset) in available_jams for offset in range(block_size)):
                            continue

                        # Cek Bentrok Guru / Kelas
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

    # FASA 2: INJEKSI KHUSUS (MEMECAH BLOK JAM JIKA KETINGGALAN UNASSIGNED)
    temp_unassigned = list(unassigned)
    for u_item in temp_unassigned:
        kelas_target = u_item['kelas']
        guru_target = u_item['guru_id']
        b_size = u_item['block_size']
        mapel_item = u_item['mapel']
        
        # Coba alokasikan per 1 JP jika 2 JP berurutan gagal
        placed_count = 0
        for day in days:
            if placed_count == b_size:
                break
            available_jams = slots_by_day.get(day, [])
            for jam in available_jams:
                if placed_count == b_size:
                    break
                
                sk = (day, jam)
                slot_kosong = True
                if sk in schedule_board:
                    for e in schedule_board[sk]:
                        if e['kelas'] == kelas_target or e['guru_id'] == guru_target:
                            slot_kosong = False
                            break
                
                if slot_kosong:
                    if sk not in schedule_board:
                        schedule_board[sk] = []
                    schedule_board[sk].append({
                        'guru_id': guru_target,
                        'nama_guru': u_item['nama_guru'],
                        'mapel': mapel_item,
                        'kelas': kelas_target
                    })
                    placed_count += 1

        if placed_count == b_size:
            unassigned.remove(u_item)

    # REKAP MENJADI DATAFRAME
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

# --- DISPLAY STREAMLIT ---
btn_generate = st.button("🚀 Generate Jadwal Sekarang", type="primary")

if btn_generate or 'df_schedule' not in st.session_state:
    with st.spinner("Sistem sedang mengolah jadwal..."):
        try:
            df_sched, unassigned_list = generate_schedule(input_data)
            st.session_state['df_schedule'] = df_sched
            st.session_state['unassigned'] = unassigned_list
        except Exception as e:
            st.error(f"Terjadi kesalahan saat membaca file: {e}")
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

# METRIK
st.markdown("---")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Slot Terisi", len(df_schedule))
m2.metric("Jumlah Kelas", df_schedule['Kelas'].nunique() if not df_schedule.empty else 0)
m3.metric("Jumlah Guru", df_schedule['ID Guru'].nunique() if not df_schedule.empty else 0)
m4.metric("Gagal (Unassigned)", len(unassigned), delta_color="inverse")

# TAB HASIL
t1, t2, t3, t4 = st.tabs(["👤 Matriks (Nama)", "🔢 Matriks (Kode)", "📋 Master Detail", "⚠️ Unassigned"])

with t1:
    st.dataframe(matrix_nama, use_container_width=True)

with t2:
    st.dataframe(matrix_kode, use_container_width=True)

with t3:
    st.dataframe(df_schedule, use_container_width=True)

with t4:
    if unassigned:
        st.warning("Data berikut belum berhasil dijadwalkan:")
        st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
    else:
        st.success("🎉 Sukses! Seluruh jadwal termasuk 'Bahasa Inggris' berhasil ter-plot 100%!")

# EXPORT EXCEL
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    matrix_nama.to_excel(writer, sheet_name='Matriks_Nama')
    matrix_kode.to_excel(writer, sheet_name='Matriks_Kode')
    df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
    if unassigned:
        pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)

st.download_button(
    label="📥 Download Excel Jadwal",
    data=buffer.getvalue(),
    file_name="Jadwal_Pelajaran_Terbaru.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
