import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="AI Schedule Generator", page_icon="🤖", layout="wide")

st.title("🤖 AI Automatic Schedule Generator")
st.write("Sistem Pembuat Jadwal Pelajaran Otomatis Bebas Bentrok dan Sesuai Aturan KBM.")

target_file = st.sidebar.text_input("File Database Excel", value="database_scheduler.xlsx")

# --- MAPPING KODE & SINGKATAN MAPEL ---
MAPEL_TO_KODE = {
    'Pendidikan Agama Islam': 'M01',
    'Pendidikan Agama Hindu': 'M02',
    'Pendidikan Agama Katholik': 'M03',
    'Pendidikan Agama Kristen': 'M04',
    'Pendidikan Pancasila': 'M05',
    'Bahasa Indonesia': 'M06',
    'Matematika': 'M07',
    'Ilmu Pengetahuan Alam': 'M08',
    'Ilmu Pengetahuan Sosial': 'M09',
    'Bahasa Inggris': 'M10',
    'Pendidikan Jasmani Olahraga dan Kesehatan': 'M11',
    'Informatika': 'M12',
    'Seni Budaya': 'M13',
    'Prakarya': 'M14',
    'Bahasa Jawa': 'M15',
    'Bimbingan Konseling': 'M16'
}

MAPEL_SHORT = {
    'Pendidikan Agama Islam': 'PAI',
    'Pendidikan Pancasila': 'PP',
    'Bahasa Indonesia': 'BIN',
    'Matematika': 'MTK',
    'Ilmu Pengetahuan Alam': 'IPA',
    'Ilmu Pengetahuan Sosial': 'IPS',
    'Bahasa Inggris': 'BIG',
    'Pendidikan Jasmani Olahraga dan Kesehatan': 'PJOK',
    'Informatika': 'INF',
    'Seni Budaya': 'SNB',
    'Prakarya': 'PRK',
    'Bahasa Jawa': 'BJW',
    'Bimbingan Konseling': 'BK'
}

def clean_first_name(nama_full):
    """Mengambil nama depan saja secara bersih (tanpa gelar)."""
    if pd.isna(nama_full):
        return ""
    clean_str = re.sub(r'[,.].*', '', str(nama_full)).strip()
    words = clean_str.split()
    return words[0] if words else ""

def parse_slot_list(val):
    if pd.isna(val):
        return []
    return [int(x.strip()) for x in str(val).split(',') if x.strip().isdigit()]

# --- LOGIKA PENYUSUNAN JADWAL (SOLVER) ---
def generate_schedule(excel_path):
    xls = pd.ExcelFile(excel_path)
    guru_df = pd.read_excel(xls, 'Guru')
    slot_df = pd.read_excel(xls, 'Slot')
    gm_df = pd.read_excel(xls, 'Guru_Mengajar')

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

                # 2. Cek Validasi Max 2 JP per hari di kelas yang sama (kecuali mapel yang JP-nya 3)
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


# --- TOMBOL RUN ---
col_btn1, col_btn2 = st.columns([2, 8])
with col_btn1:
    btn_generate = st.button("🚀 Generate Jadwal Sekarang", type="primary", use_container_width=True)

if btn_generate or 'df_schedule' in st.session_state:
    if btn_generate:
        with st.spinner("Sedang mengoptimalkan jadwal... Mohon tunggu."):
            try:
                df_schedule, unassigned = generate_schedule(target_file)
                st.session_state['df_schedule'] = df_schedule
                st.session_state['unassigned'] = unassigned
                st.success("Jadwal berhasil dibuat!")
            except Exception as e:
                st.error(f"Terjadi kesalahan saat memproses data: {e}")
                st.stop()

    df_schedule = st.session_state['df_schedule']
    unassigned = st.session_state['unassigned']

    # --- MEMBUAT 2 JENIS MATRIKS ---
    # Tampilan 1: Nama Depan Guru & Singkatan Mapel
    df_schedule['Display_Nama'] = df_schedule['Mapel Singkat'] + "\n(" + df_schedule['Nama Guru'] + ")"
    matrix_nama = df_schedule.pivot_table(
        index=['Hari', 'Jam'], columns='Kelas', values='Display_Nama', aggfunc='first'
    ).fillna('-')

    # Tampilan 2: Kode Mapel & ID Guru
    df_schedule['Display_Kode'] = df_schedule['Kode Mapel'] + " (" + df_schedule['ID Guru'] + ")"
    matrix_kode = df_schedule.pivot_table(
        index=['Hari', 'Jam'], columns='Kelas', values='Display_Kode', aggfunc='first'
    ).fillna('-')

    # --- RINGKASAN STATISTIK ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Slot Terisi", len(df_schedule))
    with m2:
        st.metric("Jumlah Kelas", df_schedule['Kelas'].nunique() if not df_schedule.empty else 0)
    with m3:
        st.metric("Jumlah Guru", df_schedule['ID Guru'].nunique() if not df_schedule.empty else 0)
    with m4:
        st.metric("Gagal Dijadwalkan", len(unassigned), delta_color="inverse")

    st.markdown("---")

    # --- TAB HASIL JADWAL ---
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

    # --- DOWNLOAD EXCEL ---
    st.markdown("---")
    st.subheader("📥 Export Hasil Jadwal ke Excel")
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        matrix_nama.to_excel(writer, sheet_name='Matriks_Nama_Guru')
        matrix_kode.to_excel(writer, sheet_name='Matriks_Kode_Mapel')
        df_schedule.to_excel(writer, sheet_name='Master_Detail', index=False)
        if unassigned:
            pd.DataFrame(unassigned).to_excel(writer, sheet_name='Unassigned', index=False)
            
    st.download_button(
        label="📥 Download Hasil Jadwal (Excel)",
        data=buffer.getvalue(),
        file_name="Hasil_Jadwal_Pelajaran.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
