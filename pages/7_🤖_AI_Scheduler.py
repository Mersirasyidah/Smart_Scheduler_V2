# ==========================================
# 2. ANTARMUKA STREAMLIT (UI) & LAPORAN SEMUA KELAS
# ==========================================

st.set_page_config(page_title="AI Scheduler Engine", page_icon="🤖", layout="wide")

st.title("🤖 AI Smart Scheduler Engine")
st.markdown("Sistem penyusun jadwal otomatis berbasis **Constraint Programming (OR-Tools)**.")

# Inisialisasi Session State jika belum ada
if 'assignments' not in st.session_state:
    st.session_state.assignments = [
        {"id": 1, "kelas": "9A", "mapel_code": "M08", "mapel": "Bahasa Indonesia", "guru_id": "G01", "guru_nama": "Purwanto, S.Pd.", "splits": [2, 2]},
        {"id": 2, "kelas": "9A", "mapel_code": "M09", "mapel": "Bahasa Inggris", "guru_id": "G02", "guru_nama": "Asti Am Rini, S.Pd.", "splits": [2, 2]},
        {"id": 3, "kelas": "9A", "mapel_code": "M11", "mapel": "Matematika", "guru_id": "G03", "guru_nama": "Luthfan Qaedi W.", "splits": [3, 2]},
        {"id": 4, "kelas": "8A", "mapel_code": "M08", "mapel": "Bahasa Indonesia", "guru_id": "G01", "guru_nama": "Purwanto, S.Pd.", "splits": [2, 2]},
        {"id": 5, "kelas": "8A", "mapel_code": "M11", "mapel": "Matematika", "guru_id": "G04", "guru_nama": "Anggi Supriyadi, S.Hum", "splits": [3, 2]},
    ]

if 'teachers_info' not in st.session_state:
    st.session_state.teachers_info = {
        'G01': {'status': 'PERMANENT', 'mgmp_day': 'Selasa'},
        'G02': {'status': 'PERMANENT', 'mgmp_day': 'Rabu'},
        'G03': {'status': 'GTT', 'mgmp_day': 'Kamis'},
        'G04': {'status': 'GTT', 'mgmp_day': 'Jumat'},
    }

# Sidebar Konfigurasi
st.sidebar.header("⚙️ Konfigurasi Parameter")
days = st.sidebar.multiselect(
    "Hari Sekolah",
    ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
    default=["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]
)
max_hours = st.sidebar.number_input("Maksimal Jam ke- per Hari", 1, 10, value=9)

st.subheader("📋 Data Input Penugasan & Guru")
col1, col2 = st.columns(2)
with col1:
    st.write("**Daftar Penugasan Mapel (Assignments)**")
    st.dataframe(pd.DataFrame(st.session_state.assignments), use_container_width=True)
with col2:
    st.write("**Data Guru & MGMP (Teachers Info)**")
    st.json(st.session_state.teachers_info)

st.divider()

# --- TOMBOL RUN GENERATE JADWAL ---
if st.button("🚀 Generate Laporan Jadwal Semua Kelas", type="primary"):
    with st.spinner("Menyusun dan mengoptimalkan jadwal seluruh kelas..."):
        solver = SchedulerSolver(
            assignments=st.session_state.assignments,
            days=days,
            max_hours_per_day=max_hours
        )
        
        results_df = solver.solve(
            mgmp_constraints=st.session_state.teachers_info,
            teachers_info=st.session_state.teachers_info
        )

    if results_df is not None and not results_df.empty:
        st.success("✅ Jadwal Seluruh Kelas Berhasil Disusun Lengkap!")
        
        # Gabungkan Informasi Mapel + Guru untuk Tampilan Laporan Ringkas
        results_df['Display'] = results_df['Kode Mapel'] + " (" + results_df['Guru'] + ")"
        
        st.header("📊 LAPORAN JADWAL PELAJARAN SEMUA KELAS")
        st.caption("Jadwal dari Hari Senin sampai Jumat")

        # TAB MODES
        tab1, tab2, tab3 = st.tabs(["🗓️ Laporan Master (Semua Kelas)", "🏫 Laporan per Kelas", "📄 Data Mentah / Export"])

        # TAB 1: LAPORAN MASTER SEMUA KELAS (SENIN - JUMAT)
        with tab1:
            for day in days:
                st.markdown(f"### 📌 Hari: {day.upper()}")
                df_day = results_df[results_df['Hari'] == day]
                
                if not df_day.empty:
                    # Pivot Table: Baris = Jam ke-, Kolom = Kelas
                    pivot_day = df_day.pivot(index='Jam', columns='Kelas', values='Display').fillna("-")
                    st.table(pivot_day)
                else:
                    st.info(f"Tidak ada kegiatan KBM di hari {day}.")
                st.divider()

        # TAB 2: LAPORAN PER KELAS (DIPISAH DENGAN TAB)
        with tab2:
            all_classes = sorted(results_df['Kelas'].unique())
            class_tabs = st.tabs([f"Kelas {c}" for c in all_classes])
            
            for idx, c_name in enumerate(all_classes):
                with class_tabs[idx]:
                    df_class = results_df[results_df['Kelas'] == c_name]
                    pivot_class = df_class.pivot(index='Jam', columns='Hari', values='Display').fillna("-")
                    
                    # Reorder kolom hari agar berurutan
                    existing_days = [d for d in days if d in pivot_class.columns]
                    pivot_class = pivot_class[existing_days]
                    
                    st.markdown(f"#### 🎓 Jadwal Pelajaran Kelas **{c_name}**")
                    st.table(pivot_class)

        # TAB 3: DOWNLOAD DATASET
        with tab3:
            st.dataframe(results_df[['Hari', 'Jam', 'Kelas', 'Kode Mapel', 'Mapel', 'Guru']], use_container_width=True)
            
            csv_data = results_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV Laporan Jadwal",
                data=csv_data,
                file_name="laporan_jadwal_semua_kelas.csv",
                mime="text/csv"
            )
    else:
        st.error("❌ Gagal membuat jadwal. Batasan (constraints) terlalu ketat atau slot jam tidak mencukupi.")
