import streamlit as st
import pandas as pd
import io
import traceback
from scheduler_core.solver import SchedulerSolver

# -----------------------------------------------------------------------------
# 1. KONFIGURASI HALAMAN STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistem Penjadwalan Sekolah",
    page_icon="📅",
    layout="wide"
)

# Custom CSS untuk mempercantik tampilan tabel matriks
st.markdown("""
<style>
    .dataframe {
        font-size: 13px !important;
        text-align: center !important;
    }
    th {
        background-color: #f0f2f6 !important;
        text-align: center !important;
        font-weight: bold !important;
    }
    td {
        vertical-align: middle !important;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 2. FUNGSI DIAGNOSTIK & VALIDASI DATA MASTER
# -----------------------------------------------------------------------------
def validate_data(guru_df, rombel_df, mengajar_df, slot_df):
    """Mengecek kelayakan data sebelum dikirim ke solver"""
    warnings = []
    
    if mengajar_df is not None and slot_df is not None and rombel_df is not None:
        jp_col = next((c for c in mengajar_df.columns if 'jp' in c.lower() or 'jam' in c.lower()), None)
        
        if jp_col:
            total_jp_butuh = mengajar_df[jp_col].sum()
            total_slot_tersedia = len(slot_df) * len(rombel_df)
            
            if total_jp_butuh > total_slot_tersedia:
                warnings.append(
                    f"⚠️ **Total JP Kurang Slot:** Total kebutuhan mengajar = **{total_jp_butuh} JP**, "
                    f"tetapi kapasitas slot kelas yang tersedia hanya **{total_slot_tersedia} JP** "
                    f"({len(slot_df)} slot × {len(rombel_df)} rombel)."
                )

        guru_id_col = next((c for c in mengajar_df.columns if 'guru' in c.lower()), None)
        if jp_col and guru_id_col:
            jp_per_guru = mengajar_df.groupby(guru_id_col)[jp_col].sum()
            max_slot_guru = len(slot_df)
            guru_overload = jp_per_guru[jp_per_guru > max_slot_guru]
            
            if not guru_overload.empty:
                for g_id, total_g_jp in guru_overload.items():
                    warnings.append(
                        f"⚠️ **Guru Overload:** Guru `{g_id}` memiliki beban **{total_g_jp} JP**, "
                        f"padahal total slot waktu seminggu hanya **{max_slot_guru} slot**."
                    )

    return warnings


# -----------------------------------------------------------------------------
# 3. FUNGSI TAMPILAN JADWAL MATRIKS PER HARI (7A - 9E)
# -----------------------------------------------------------------------------
def tampilkan_jadwal_per_hari(df_hasil):
    st.subheader("📅 Hasil Jadwal Mengajar Per Hari (Seluruh Kelas)")
    
    if df_hasil.empty:
        st.warning("Belum ada data jadwal yang dihasilkan.")
        return

    daftar_hari = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
    
    for hari in daftar_hari:
        df_hari = df_hasil[df_hasil['Hari'] == hari].copy()
        
        if df_hari.empty:
            continue
            
        st.markdown(f"#### 📌 Hari {hari}")
        
        # Format tampilan cell: Mapel + Nama Guru (jika ada)
        def format_cell(row):
            if row['Mapel'] == 'Upacara':
                return "<b> Upacara </b>"
            elif row['Guru'] != '-':
                return f"<b>{row['Mapel']}</b><br><small style='color:#555;'>({row['Guru']})</small>"
            else:
                return f"<b>{row['Mapel']}</b>"

        df_hari['Detail'] = df_hari.apply(format_cell, axis=1)
        
        # Pivot Table: Jam_Ke sebagai Baris, Rombel sebagai Kolom
        try:
            matrix = df_hari.pivot(index='Jam_Ke', columns='Rombel', values='Detail').fillna("-")
            
            # Tampilkan sebagai HTML yang diformat rapi
            st.write(matrix.to_html(escape=False), unsafe_allow_html=True)
            st.write("") # Spasi antar tabel hari
        except Exception as e:
            st.error(f"Gagal memformat tabel untuk hari {hari}: {e}")
        
        st.divider()


# -----------------------------------------------------------------------------
# 4. APLIKASI UTAMA (STREAMLIT UI)
# -----------------------------------------------------------------------------
def main():
    st.title("🗓️ Generator Jadwal Pelajaran Sekolah Auto-Solver")
    st.write("Aplikasi otomatisasi penyusunan jadwal berbasis Constraint Programming (OR-Tools).")
    
    st.sidebar.header("⚙️ Pengaturan & Data Master")
    
    # Upload File Excel Data Master
    uploaded_file = st.sidebar.file_uploader("Unggah File Excel Data Master", type=["xlsx", "xls"])
    
    # Setting Timeout
    timeout = st.sidebar.slider("Batas Timeout Solver (detik)", min_value=30, max_value=600, value=120, step=30)
    
    if uploaded_file is not None:
        try:
            excel_file = pd.ExcelFile(uploaded_file)
            
            # Membaca Sheet Excel
            guru_df = pd.read_excel(excel_file, sheet_name='Guru') if 'Guru' in excel_file.sheet_names else None
            rombel_df = pd.read_excel(excel_file, sheet_name='Rombel') if 'Rombel' in excel_file.sheet_names else None
            mengajar_df = pd.read_excel(excel_file, sheet_name='Guru_Mengajar') if 'Guru_Mengajar' in excel_file.sheet_names else None
            mapel_df = pd.read_excel(excel_file, sheet_name='Mapel') if 'Mapel' in excel_file.sheet_names else None
            slot_df = pd.read_excel(excel_file, sheet_name='Hari_Jam') if 'Hari_Jam' in excel_file.sheet_names else None

            # Tampilkan Preview Data Ringkas
            with st.expander("👁️ Lihat Data Master yang Diunggah", expanded=False):
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["Guru", "Rombel", "Guru_Mengajar", "Mapel", "Hari_Jam"])
                if guru_df is not None: tab1.dataframe(guru_df)
                if rombel_df is not None: tab2.dataframe(rombel_df)
                if mengajar_df is not None: tab3.dataframe(mengajar_df)
                if mapel_df is not None: tab4.dataframe(mapel_df)
                if slot_df is not None: tab5.dataframe(slot_df)

            # Tombol Eksekusi
            if st.button("🚀 Generate Jadwal", type="primary"):
                # 1. Jalankan Validasi Data
                warnings = validate_data(guru_df, rombel_df, mengajar_df, slot_df)
                if warnings:
                    st.warning("🔍 **Peringatan Keselarasan Data Master:**")
                    for w in warnings:
                        st.write(w)
                    st.divider()

                # 2. Penentuan Days & Max Hours
                days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
                max_hours = 8

                if slot_df is not None and not slot_df.empty:
                    if 'Hari' in slot_df.columns:
                        days = slot_df['Hari'].dropna().unique().tolist()
                    for jam_col in ['Jam_Ke', 'Jam', 'JamKe']:
                        if jam_col in slot_df.columns:
                            max_hours = int(slot_df[jam_col].max())
                            break

                data_dict = {
                    "guru": guru_df,
                    "rombel": rombel_df,
                    "mengajar": mengajar_df,
                    "mapel": mapel_df,
                    "slot": slot_df
                }

                # 3. Jalankan Solver
                with st.spinner("⏳ Sedang memproses dan mencari kombinasi jadwal terbaik... Mohon tunggu."):
                    solver_instance = SchedulerSolver(data_dict, days, max_hours)
                    success = solver_instance.solve(time_limit=timeout)

                if success:
                    st.success("✅ Jadwal Berhasil Dibuat!")
                    
                    df_hasil = solver_instance.extract_results()
                    
                    # 4. Tampilkan Jadwal Matriks per Hari
                    tampilkan_jadwal_per_hari(df_hasil)
                    
                    # 5. Fitur Unduh Hasil ke Excel
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_hasil.to_excel(writer, sheet_name='Jadwal_Lengkap', index=False)
                        
                        # Buat Sheet Per Hari
                        for h in days:
                            df_h = df_hasil[df_hasil['Hari'] == h]
                            if not df_h.empty:
                                pvt = df_h.pivot(index='Jam_Ke', columns='Rombel', values='Mapel')
                                pvt.to_excel(writer, sheet_name=f'Hari_{h}')
                                
                    processed_data = output.getvalue()
                    st.download_button(
                        label="📥 Download Hasil Jadwal (Excel)",
                        data=processed_data,
                        file_name="Hasil_Jadwal_Pelajaran.xlsx",
                        mime="application/vnd.ms-excel"
                    )

                else:
                    st.error("❌ Solver tidak dapat menemukan kombinasi jadwal yang cocok.")
                    st.info(
                        "💡 **Saran Perbaikan:**\n"
                        "1. Pastikan batas Timeout cukup tinggi (misal: 300 detik).\n"
                        "2. Cek kembali kolom `Slot` di sheet `Guru_Mengajar` (format contoh: `2,2,1`).\n"
                        "3. Pastikan jam mengajar guru tidak melampaui aturan MGMP yang ditentukan."
                    )

        except Exception as e:
            st.error(f"❌ Terjadi kesalahan saat membaca file Excel: {e}")
            st.code(traceback.format_exc())

    else:
        st.info("👈 Silakan unggah file Excel Data Master terlebih dahulu di panel sebelah kiri untuk memulai.")


if __name__ == "__main__":
    main()
