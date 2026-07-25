import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="AI Schedule Generator", page_icon="🤖", layout="wide")

st.title("🤖 AI Automatic Schedule Generator")
st.write("Sistem Pembuat Jadwal Pelajaran Otomatis Bebas Bentrok dan Sesuai Aturan KBM.")

# --- SIDEBAR & FILE INPUT ---
st.sidebar.header("📁 Input Database")
uploaded_file = st.sidebar.file_uploader("Upload File Database Excel", type=["xlsx", "xls"])
target_file_path = st.sidebar.text_input("Atau ketik jalur file lokal:", value="database_scheduler.xlsx")

input_data = uploaded_file if uploaded_file is not None else target_file_path

# --- MAPPING KODE & SINGKATAN MAPEL ---
MAPEL_TO_KODE = {
    'pendidikan agama islam': 'M01', 'pai': 'M01',
    'pendidikan agama hindu': 'M02',
    'pendidikan agama katholik': 'M03',
    'pendidikan agama kristen': 'M04',
    'pendidikan pancasila': 'M05', 'pp': 'M05', 'pkn': 'M05',
    'bahasa indonesia': 'M06', 'b. indonesia': 'M06', 'bin': 'M06',
    'matematika': 'M07', 'mtk': 'M07',
    'ilmu pengetahuan alam': 'M08', 'ipa': 'M08',
    'ilmu pengetahuan sosial': 'M09', 'ips': 'M09',
    'bahasa inggris': 'M10', 'b. inggris': 'M10', 'b.inggris': 'M10', 'big': 'M10',
    'pendidikan jasmani olahraga dan kesehatan': 'M11', 'pjok': 'M11',
    'informatika': 'M12', 'inf': 'M12',
    'seni budaya': 'M13', 'snb': 'M13',
    'prakarya': 'M14', 'prk': 'M14',
    'bahasa jawa': 'M15', 'b. jawa': 'M15', 'bjw': 'M15',
    'bimbingan konseling': 'M16', 'bk': 'M16'
}

MAPEL_SHORT = {
    'pendidikan agama islam': 'PAI', 'pai': 'PAI',
    'pendidikan pancasila': 'PP', 'pp': 'PP',
    'bahasa indonesia': 'BIN', 'bin': 'BIN',
    'matematika': 'MTK', 'mtk': 'MTK',
    'ilmu pengetahuan alam': 'IPA', 'ipa': 'IPA',
    'ilmu pengetahuan sosial': 'IPS', 'ips': 'IPS',
    'bahasa inggris': 'BIG', 'b. inggris': 'BIG', 'b.inggris': 'BIG', 'big': 'BIG',
    'pendidikan jasmani olahraga dan kesehatan': 'PJOK', 'pjok': 'PJOK',
    'informatika': 'INF', 'inf': 'INF',
    'seni budaya': 'SNB', 'snb': 'SNB',
    'prakarya': 'PRK', 'prk': 'PRK',
    'bahasa jawa': 'BJW', 'bjw': 'BJW',
    'bimbingan konseling': 'BK', 'bk': 'BK'
}

def clean_first_name(nama_full):
    if pd.isna(nama_full):
        return ""
    clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
    words = clean_str.split()
    return words[0] if words else ""

def parse_slot_list(val):
    if pd.isna(val):
        return []
    return [int(x.strip()) for x in str(val).split(',') if str(x).strip().isdigit()]

def get_mapel_info(mapel_raw):
    m_str = str(mapel_raw).strip().lower()
    kode = MAPEL_TO_KODE.get(m_str, None)
    singkatan = MAPEL_SHORT.get(m_str, None)
    
    if not kode:
        if 'pancasila' in m_str or 'pp' in m_str or 'pkn' in m_str:
            kode, singkatan = 'M05', 'PP'
        elif 'inggris' in m_str or 'big' in m_str:
            kode, singkatan = 'M10', 'BIG'
        elif 'matematika' in m_str or 'mtk' in m_str:
            kode, singkatan = 'M07', 'MTK'
        elif 'jasmani' in m_str or 'pjok' in m_str:
            kode, singkatan = 'M11', 'PJOK'
        else:
            kode = 'MXX'
            singkatan = str(mapel_raw).strip()[:4].upper()
            
    if not singkatan:
        singkatan = 'BIG' if kode == 'M10' else str(mapel_raw).strip()[:4].upper()
        
    return kode, singkatan

def get_sheet_df(xls, target_name):
    target_clean = re.sub(r'[^a-zA-Z0-9]', '', str(target_name)).lower()
    for sheet in xls.sheet_names:
        sheet_clean = re.sub(r'[^a-zA-Z0-9]', '', str(sheet)).lower()
        if target_clean == sheet_clean:
            df = pd.read_excel(xls, sheet)
            df.columns = [str(c).strip() for c in df.columns]
            return df

    for sheet in xls.sheet_names:
        sheet_clean = re.sub(r'[^a-zA-Z0-9]', '', str(sheet)).lower()
        if target_clean in sheet_clean:
            df = pd.read_excel(xls, sheet)
            df.columns = [str(c).strip() for c in df.columns]
            return df
    
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan! Sheet di Excel ini: {xls.sheet_names}.")

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

    # Prioritas Pemplotan
    def get_priority(item):
        mapel = str(item['Mapel']).lower()
        kelas = str(item['Kelas'])
        is_pjok = 'jasmani' in mapel or 'olahraga' in mapel or 'pjok' in mapel or 'm11' in mapel
        is_mtk_ipa = 'matematika' in mapel or 'mtk' in mapel or 'ilmu pengetahuan alam' in mapel or 'ipa' in mapel
        is_inggris = 'inggris' in mapel or 'big' in mapel or 'm10' in mapel
        is_kelas_9 = kelas.startswith('9')

        if is_pjok and is_kelas_9:
            return (0, -item.get('JP', 0))
        elif is_mtk_ipa and is_kelas_9:
            return (1, -item.get('JP', 0))
        elif is_pjok:
            return (2, -item.get('JP', 0))
        elif is_inggris:
            return (3, -item.get('JP', 0))
        else:
            return (4, -item.get('JP', 0))

    records.sort(key=get_priority)

    schedule_board = {}
    pjok_day_kelas9 = {}
    unassigned = []

    for item in records:
        guru_id = item['ID Guru']
        guru_nama = item['Nama Guru']
        mapel = item['Mapel']
        kelas = item['Kelas']
        slot_blocks = item.get('Slot_List', [])

        mapel_lower = str(mapel).lower()
        is_pjok = 'jasmani' in mapel_lower or 'olahraga' in mapel_lower or 'pjok' in mapel_lower
        is_mtk_ipa = 'matematika' in mapel_lower or 'mtk' in mapel_lower or 'ilmu pengetahuan alam' in mapel_lower or 'ipa' in mapel_lower
        is_kelas_9 = str(kelas).startswith('9')

        for block_size in slot_blocks:
            placed = False
            
            for mode in ['strict', 'fallback']:
                if placed:
                    break

                for day in days:
                    if placed:
                        break

                    # 1. ATURAN PISAH HARI (Maksimal 1 blok per mapel per kelas per hari)
                    existing_jp_in_day = 0
                    for (h, _), entries in schedule_board.items():
                        if h == day:
                            for e in entries:
                                if e['kelas'] == kelas and str(e['mapel']).strip().lower() == mapel_lower:
                                    existing_jp_in_day += 1

                    if existing_jp_in_day > 0:
                        continue

                    # 2. ATURAN MGMP & STATUS GURU
                    mgmp_day = str(mgmp_days.get(guru_id, '')).strip().lower()
                    status = str(guru_status.get(guru_id, '')).strip().upper()
                    is_mgmp_day = (mgmp_day == day.lower())

                    if is_mgmp_day and status == 'GTT':
                        continue

                    available_jams = slots_by_day.get(day, [])
                    
                    for jam in available_jams:
                        if is_mgmp_day and status != 'GTT' and mode == 'strict':
                            if (jam + block_size - 1) > 3:
                                continue

                        if not all((jam + offset) in available_jams for offset in range(block_size)):
                            continue

                        # Mode Strict: Aturan khusus kelas 9
                        if mode == 'strict':
                            if is_kelas_9 and is_pjok:
                                if jam != 3 or block_size != 3:
                                    continue

                            if is_kelas_9 and is_mtk_ipa and block_size == 2:
                                target_pjok_day = pjok_day_kelas9.get(kelas)
                                if target_pjok_day and day == target_pjok_day:
                                    if jam != 1:
                                        continue

                        # 3. CEK BENTROK GURU & KELAS
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
                            
                            if is_kelas_9 and is_pjok:
                                pjok_day_kelas9[kelas] = day

                            placed = True
                            break

            if not placed:
                unassigned.append({
                    'guru_id': guru_id,
                    'kelas': kelas,
                    'mapel': mapel,
                    'block_size': block_size
                })

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


# --- TOMBOL RUN JADWAL ---
btn_generate = st.button("🚀 Generate Jadwal Sekarang", type="primary", use_container_width=False)

if btn_generate or 'df_schedule' not in st.session_state:
    with st.spinner("Sedang memproses dan mengoptimalkan jadwal..."):
        try:
            df_sched, unassigned_list = generate_schedule(input_data)
            st.session_state['df_schedule'] = df_sched
            st.session_state['unassigned'] = unassigned_list
        except Exception as e:
            st.error(f"Gagal membaca/memproses file Excel: {e}")
            st.stop()

df_schedule = st.session_state['df_schedule']
unassigned = st.session_state['unassigned']

# --- MEMBUAT TABEL MATRIKS ---
df_schedule['Display_Nama'] = df_schedule['Mapel Singkat'] + "\n(" + df_schedule['Nama Guru'] + ")"
matrix_nama = df_schedule.pivot_table(
    index=['Hari', 'Jam'], columns='Kelas', values='Display_Nama', aggfunc='first'
).fillna('-')

df_schedule['Display_Kode'] = df_schedule['Kode Mapel'] + " (" + df_schedule['ID Guru'] + ")"
matrix_kode = df_schedule.pivot_table(
    index=['Hari', 'Jam'], columns='Kelas', values='Display_Kode', aggfunc='first'
).fillna('-')

# --- DISPLAY DASHBOARD ---
st.markdown("---")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Total Slot Terisi", len(df_schedule))
with m2:
    st.metric("Jumlah Kelas", df_schedule['Kelas'].nunique() if not df_schedule.empty else 0)
with m3:
    st.metric("Jumlah Guru", df_schedule['ID Guru'].nunique() if not df_schedule.empty else 0)
with m4:
    st.metric("Gagal Dijadwalkan", len(unassigned), delta_color="inverse")

# --- TABS BROWSER HASIL ---
tab_nama, tab_kode, tab_detail, tab_unassigned = st.tabs([
    "👤 Matriks (Nama Guru)", 
    "🔢 Matriks (Kode Mapel)", 
    "📋 Master List", 
    "⚠️ Unassigned"
])

with tab_nama:
    st.subheader("1. Tampilan Matriks: Singkatan Mapel & Nama Depan Guru")
    st.caption("Contoh isi sel: BIG (Lestari)")
    st.dataframe(matrix_nama, use_container_width=True)

with tab_kode:
    st.subheader("2. Tampilan Matriks: Kode Mapel & ID Guru")
    st.caption("Contoh isi sel: M10 (G03 / G05 / G29)")
    st.dataframe(matrix_kode, use_container_width=True)

with tab_detail:
    st.subheader("Master List Detail Jadwal")
    st.dataframe(df_schedule, use_container_width=True)

with tab_unassigned:
    st.subheader("Daftar Jam Mengajar yang Gagal Dijadwalkan")
    if unassigned:
        st.warning(f"Terdapat {len(unassigned)} alokasi jam mengajar yang tidak mendapat slot.")
        st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
    else:
        st.success("🎉 Luar biasa! Semua jadwal 100% berhasil di-plot tanpa unassigned.")

# --- DOWNLOAD BUTTON ---
st.markdown("---")
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    matrix_nama.to_excel(writer, sheet_name='Matriks_Nama_Guru')
    matrix_kode.to_excel(writer, sheet_name='Matriks_Kode_Mapel')
    df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
    if unassigned:
        pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)

st.download_button(
    label="📥 Download Hasil Jadwal ke Excel",
    data=buffer.getvalue(),
    file_name="Hasil_Jadwal_Pelajaran.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
