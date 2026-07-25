import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="AI Schedule Generator", page_icon="🤖", layout="wide")

st.title("🤖 AI Automatic Schedule Generator")
st.write("Sistem Plotting Jadwal Otomatis: Memasukkan Semua Guru ke Slot Kelas.")

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
        if target_clean == sheet_clean or target_clean in sheet_clean:
            df = pd.read_excel(xls, sheet)
            df.columns = [str(c).strip() for c in df.columns]
            return df
    raise ValueError(f"Sheet '{target_name}' tidak ditemukan! Sheet yang ada: {xls.sheet_names}.")

# --- ENGINE ALGORITMA JADWAL (SISTEM PAKSA SLOT KELAS) ---
def generate_schedule(excel_source):
    xls = pd.ExcelFile(excel_source)
    guru_df = get_sheet_df(xls, 'Guru')
    slot_df = get_sheet_df(xls, 'Slot')
    gm_df = get_sheet_df(xls, 'Guru_Mengajar')

    # Pembersihan Slot KBM (Membuang Istirahat / Upacara / Sholat)
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
    all_kbm_slots = []
    for d in days:
        jams = kbm_slots[kbm_slots['Hari'].astype(str).str.strip().str.capitalize() == d]['Jam'].tolist()
        sorted_jams = sorted(list(set(jams)))
        slots_by_day[d] = sorted_jams
        for j in sorted_jams:
            all_kbm_slots.append((d, j))

    slot_col = 'Slot'
    for c in gm_df.columns:
        if any(kw in c.lower() for kw in ['slot', 'alokasi', 'jp', 'jam']):
            slot_col = c
            break

    gm_df['Slot_List'] = gm_df[slot_col].apply(parse_slot_list)
    gm_df['ID Guru'] = gm_df['ID Guru'].astype(str).str.strip()

    # Ekstrak seluruh item penugasan
    assignments = []
    for _, item in gm_df.iterrows():
        guru_id = str(item['ID Guru']).strip()
        guru_nama = item['Nama Guru']
        mapel = item['Mapel']
        kelas = item['Kelas']
        slot_blocks = item.get('Slot_List', [])

        for block in slot_blocks:
            assignments.append({
                'guru_id': guru_id,
                'nama_guru': guru_nama,
                'mapel': mapel,
                'kelas': kelas,
                'block_size': block
            })

    # Urutkan penugasan dari ukuran blok terbesar agar blok 3/2 JP terpasang dulu
    assignments.sort(key=lambda x: x['block_size'], reverse=True)

    schedule_board = {}
    unassigned = []

    for item in assignments:
        guru_id = item['guru_id']
        guru_nama = item['nama_guru']
        mapel = item['mapel']
        kelas = item['kelas']
        block_size = item['block_size']

        placed = False

        # TAHAP 1: Coba alokasi blok utuh tanpa bentrok
        for day in days:
            if placed:
                break
            available_jams = slots_by_day.get(day, [])
            for jam in available_jams:
                if not all((jam + offset) in available_jams for offset in range(block_size)):
                    continue

                # Cek bentrok guru atau kelas
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

        # TAHAP 2: Jika blok utuh gagal (misal 3 JP tak muat), pecah menjadi jam tunggal (1 JP)
        if not placed:
            placed_count = 0
            for day in days:
                for jam in slots_by_day.get(day, []):
                    if placed_count == block_size:
                        break
                    slot_key = (day, jam)
                    bentrok = False
                    if slot_key in schedule_board:
                        for e in schedule_board[slot_key]:
                            if e['guru_id'] == guru_id or e['kelas'] == kelas:
                                bentrok = True
                                break
                    if not bentrok:
                        if slot_key not in schedule_board:
                            schedule_board[slot_key] = []
                        schedule_board[slot_key].append({
                            'guru_id': guru_id,
                            'nama_guru': guru_nama,
                            'mapel': mapel,
                            'kelas': kelas
                        })
                        placed_count += 1

            if placed_count == block_size:
                placed = True
            elif placed_count > 0:
                # Sisa jam yang gagal terpasang dari pemecahan blok
                unassigned.append({
                    'guru_id': guru_id,
                    'nama_guru': guru_nama,
                    'kelas': kelas,
                    'mapel': mapel,
                    'block_size': block_size - placed_count
                })
                placed = True  # Sebagian sudah terisi

        # TAHAP 3: Jika sama sekali tidak bisa dipasang
        if not placed:
            unassigned.append({
                'guru_id': guru_id,
                'nama_guru': guru_nama,
                'kelas': kelas,
                'mapel': mapel,
                'block_size': block_size
            })

    rows = []
    for (hari, jam), list_entries in schedule_board.items():
        for e in list_entries:
            nama_depan = clean_first_name(e['nama_guru'])
            kode_mapel, mapel_singkat = get_mapel_info(e['mapel'])

            rows.append({
                'Hari': hari,
                'Jam': jam,
                'Kelas': e['kelas'],
                'ID Guru': e['guru_id'],
                'Nama Guru Full': e['nama_guru'],
                'Nama Guru': nama_depan,
                'Mapel Full': e['mapel'],
                'Mapel Singkat': mapel_singkat,
                'Kode Mapel': kode_mapel
            })

    return pd.DataFrame(rows), unassigned

# --- TOMBOL RUN JADWAL & PROSES ---
btn_generate = st.button("🚀 Generate Jadwal Sekarang", type="primary", use_container_width=False)

if btn_generate or 'df_schedule' not in st.session_state:
    with st.spinner("Sedang memetakan seluruh guru ke dalam slot kelas..."):
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
    matrix_nama = pd.DataFrame()
    matrix_kode = pd.DataFrame()

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
    st.metric("Jam Belum Muat", len(unassigned), delta_color="inverse")

# --- TABS BROWSER HASIL ---
tab_nama, tab_kode, tab_detail, tab_unassigned = st.tabs([
    "👤 Matriks (Nama Guru)", 
    "🔢 Matriks (Kode Mapel)", 
    "📋 Master List", 
    "⚠️ Unassigned / Belum Muat"
])

with tab_nama:
    st.subheader("1. Tampilan Matriks: Singkatan Mapel & Nama Depan Guru")
    st.caption("Lihat sel berlabel '-' untuk mengecek slot mana saja yang masih kosong di tiap kelas.")
    st.dataframe(matrix_nama, use_container_width=True)

with tab_kode:
    st.subheader("2. Tampilan Matriks: Kode Mapel & ID Guru")
    st.dataframe(matrix_kode, use_container_width=True)

with tab_detail:
    st.subheader("Master List Detail Jadwal")
    st.dataframe(df_schedule, use_container_width=True)

with tab_unassigned:
    st.subheader("Daftar Jam Mengajar yang Tidak Muat di Kelas")
    if unassigned:
        st.warning(f"Terdapat {len(unassigned)} alokasi jam mengajar yang tidak muat di slot kelas.")
        st.dataframe(pd.DataFrame(unassigned), use_container_width=True)
    else:
        st.success("🎉 Luar biasa! Semua slot kelas terisi sempurna 100% tanpa ada jam yang tersisa!")

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
    label="📥 Download Hasil Pemetaan ke Excel",
    data=buffer.getvalue(),
    file_name="Hasil_Pemetaan_Jadwal.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
