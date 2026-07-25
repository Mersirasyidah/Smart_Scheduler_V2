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

# Prioritaskan file upload jika ada, jika tidak gunakan path lokal
input_data = uploaded_file if uploaded_file is not None else target_file_path

# --- MAPPING KODE & SINGKATAN MAPEL ---
MAPEL_TO_KODE = {
    'Pendidikan Agama Islam': 'M01', 'Pendidikan Agama Hindu': 'M02',
    'Pendidikan Agama Katholik': 'M03', 'Pendidikan Agama Kristen': 'M04',
    'Pendidikan Pancasila': 'M05', 'Bahasa Indonesia': 'M06',
    'Matematika': 'M07', 'Ilmu Pengetahuan Alam': 'M08',
    'Ilmu Pengetahuan Sosial': 'M09', 'Bahasa Inggris': 'M10',
    'Pendidikan Jasmani Olahraga dan Kesehatan': 'M11', 'Informatika': 'M12',
    'Seni Budaya': 'M13', 'Prakarya': 'M14',
    'Bahasa Jawa': 'M15', 'Bimbingan Konseling': 'M16'
}

MAPEL_SHORT = {
    'Pendidikan Agama Islam': 'PAI', 'Pendidikan Pancasila': 'PP',
    'Bahasa Indonesia': 'BIN', 'Matematika': 'MTK',
    'Ilmu Pengetahuan Alam': 'IPA', 'Ilmu Pengetahuan Sosial': 'IPS',
    'Bahasa Inggris': 'BIG', 'Pendidikan Jasmani Olahraga dan Kesehatan': 'PJOK',
    'Informatika': 'INF', 'Seni Budaya': 'SNB',
    'Prakarya': 'PRK', 'Bahasa Jawa': 'BJW', 'Bimbingan Konseling': 'BK'
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

# --- FUNGSI AMAN MEMBACA SHEET EXCEL ---
def get_sheet_df(xls, target_name):
    target_clean = re.sub(r'[^a-zA-Z0-9]', '', str(target_name)).lower()
    
    # 1. Prioritaskan pencocokan eksak (Exact match)
    for sheet in xls.sheet_names:
        sheet_clean = re.sub(r'[^a-zA-Z0-9]', '', str(sheet)).lower()
        if target_clean == sheet_clean:
            df = pd.read_excel(xls, sheet)
            df.columns = [str(c).strip() for c in df.columns] # Clean column headers
            return df

    # 2. Match parsial jika eksak tidak ada
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

    # Data MGMP dan Status Guru
    mgmp_days = {}
    guru_status = {}
    if 'ID Guru' in guru_df.columns:
        if 'Hari MGMP' in guru_df.columns:
            mgmp_days = dict(zip(guru_df['ID Guru'], guru_df['Hari MGMP'].fillna('')))
        if 'Status' in guru_df.columns:
            guru_status = dict(zip(guru_df['ID Guru'], guru_df['Status'].fillna('')))

    # Penanganan fleksibel nama kolom Slot/Alokasi di Guru_Mengajar
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

    # Urutkan Prioritas: PJOK & Mapel durasi besar (3 JP) diutamakan
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
            
            # Percobaan bertahap: strict jam pagi PJOK dulu, lalu fleksibel jika tidak muat
            for strict_pjok in [True, False]:
                if placed:
                    break
                for day in days:
                    # 1. ATURAN HARI MGMP & STATUS GURU
                    mgmp_day = str(mgmp_days.get(guru_id, '')).strip().lower()
                    status = str(guru_status.get(guru_id, '')).strip().upper()
                    
                    is_mgmp_day = (mgmp_day == day.lower())

                    # Guru GTT: Libur Penuh di Hari MGMP
                    if is_mgmp_day and status == 'GTT':
                        continue

                    # 2. Max 2 JP/hari di kelas sama (kecuali mapel bertotal 3 JP)
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
                        # Guru Non-GTT (PNS/PPPK): Boleh mengajar di Hari MGMP HANYA Jam 1-3
                        if is_mgmp_day and status != 'GTT':
                            if (jam + block_size - 1) > 3:
                                continue

                        if all((jam + offset) in available_jams for offset in range(block_size)):
                            
                            # 3. Validasi Jam PJOK
                            is_pjok = 'jasmani' in str(mapel).lower() or 'olahraga' in str(mapel).lower() or 'pjok' in str(mapel).lower()
                            if is_pjok and strict_pjok:
                                tingkat = str(kelas)[0] if str(kelas)[0].isdigit() else ''
                                if tingkat in ['7', '8']:
                                    valid_jam = (jam == 2) if day == 'Senin' else (jam == 1)
                                    if not valid_jam:
                                        continue
                                elif tingkat == '9':
                                    if jam != 4:
                                        continue

                            # 4. Cek Bentrok Slot
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
    st.caption("Contoh isi sel: IPA (Purwanto)")
    st.dataframe(matrix_nama, use_container_width=True)

with tab_kode:
    st.subheader("2. Tampilan Matriks: Kode Mapel & ID Guru")
    st.caption("Contoh isi sel: M11 (G14)")
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
