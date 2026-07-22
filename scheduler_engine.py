import streamlit as st
import pandas as pd
import io
# Import kelas solver Anda
from solver import SchedulerSolver 

def jalankan_penjadwalan(scheduler_data, timeout_total=120):
    # Buat skenario percobaan dari yang paling ideal ke yang paling longgar
    skenario_list = [
        {"desc": "Ideal: Max 6 JP/Hari, MGMP Reguler Max Jam Ke-4", "max_jp": 6, "max_mgmp": 4},
        {"desc": "Relaksasi 1: Max 6 JP/Hari, MGMP Reguler Max Jam Ke-3", "max_jp": 6, "max_mgmp": 3},
        {"desc": "Relaksasi 2: Max 7 JP/Hari, MGMP Reguler Max Jam Ke-4", "max_jp": 7, "max_mgmp": 4},
        {"desc": "Darurat: Max 8 JP/Hari, MGMP Reguler Max Jam Ke-5", "max_jp": 8, "max_mgmp": 5},
    ]

    timeout_per_skenario = timeout_total // len(skenario_list)

    for i, skenario in enumerate(skenario_list, start=1):
        st.write(f"⏳ **Mencoba Skenario {i}:** {skenario['desc']}...")
        
        # Inisialisasi solver baru setiap percobaan
        solver_instance = SchedulerSolver(scheduler_data)
        
        # Eksekusi solver dengan parameter skenario
        is_success = solver_instance.run_solver(
            timeout_seconds=timeout_per_skenario,
            max_jam_mgmp_nongtt=skenario["max_mgmp"],
            max_jp_per_hari=skenario["max_jp"]
        )

        if is_success:
            st.success(f"✅ Berhasil menemukan solusi pada Skenario {i}!")
            df_hasil = solver_instance.extract_results()
            df_laporan = solver_instance.generate_teacher_report(df_hasil)
            return df_hasil, df_laporan

    # Jika semua skenario gagal
    st.error("❌ Solver gagal menemukan kombinasi. Rekomendasi: Naikkan Timeout atau cek ketersediaan jam di data Excel.")
    return pd.DataFrame(), pd.DataFrame()
