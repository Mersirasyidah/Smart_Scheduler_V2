import pandas as pd

def generate_teacher_report(df_hasil, list_guru, list_hari, jam_per_hari):
    """
    Menghasilkan laporan harian lengkap untuk setiap guru berdasarkan hasil penjadwalan.
    
    :param df_hasil: DataFrame hasil dari solver.extract_results()
    :param list_guru: List seluruh ID/Nama Guru
    :param list_hari: List nama hari (Senin, Selasa, dll.)
    :param jam_per_hari: Dict daftar jam pembelajaran per hari, contoh: {'Senin': [1,2,3,4,5,6,7,8,9]}
    """
    report_rows = []

    for guru in sorted(list_guru):
        # Filter jadwal khusus guru ini
        df_guru = df_hasil[df_hasil["ID_Guru"] == guru] if not df_hasil.empty else pd.DataFrame()

        for hari in list_hari:
            df_guru_hari = df_guru[df_guru["Hari"] == hari] if not df_guru.empty else pd.DataFrame()
            jam_tersedia = jam_per_hari.get(hari, [])

            if df_guru_hari.empty:
                # Guru tidak ada jadwal di hari ini (Libur)
                report_rows.append({
                    "ID_Guru": guru,
                    "Hari": hari,
                    "Status": "LIBUR / TIDAK MENGAJAR",
                    "Total_JP": 0,
                    "Detail_Mengajar": "-",
                    "Jam_Kosong_Sela": "-"
                })
            else:
                # Guru mengajar di hari ini
                df_sorted = df_guru_hari.sort_values(by="Jam_Ke")
                jam_mengajar = df_sorted["Jam_Ke"].tolist()
                total_jp = len(jam_mengajar)

                # 1. Format Ringkasan Detail Mengajar (Menggabungkan jam berurutan)
                detail_list = []
                for _, r in df_sorted.iterrows():
                    detail_list.append(f"Jam {r['Jam_Ke']} ({r['ID_Rombel']} - {r['ID_Mapel']})")
                detail_str = ", ".join(detail_list)

                # 2. Deteksi Jam Kosong Sela (Gap di antara jam mengajar awal dan akhir)
                jam_min = min(jam_mengajar)
                jam_max = max(jam_mengajar)
                
                # Jam-jam di antara jam mengajar pertama dan terakhir yang tidak diisi
                jam_sela = [
                    j for j in jam_tersedia 
                    if jam_min < j < jam_max and j not in jam_mengajar
                ]
                
                jam_sela_str = ", ".join([f"Jam ke-{j}" for j in jam_sela]) if jam_sela else "Tidak Ada (Kontinu)"

                report_rows.append({
                    "ID_Guru": guru,
                    "Hari": hari,
                    "Status": "MENGAJAR",
                    "Total_JP": total_jp,
                    "Detail_Mengajar": detail_str,
                    "Jam_Kosong_Sela": jam_sela_str
                })

    df_laporan = pd.DataFrame(report_rows)
    return df_laporan


def print_formatted_report(df_laporan):
    """
    Mencetak laporan ke terminal dengan format ringkas dan mudah dibaca per guru.
    """
    print("\n==================================================================================")
    print("                         LAPORAN DETAIL JADWAL GURU                               ")
    print("==================================================================================\n")

    for guru, group in df_laporan.groupby("ID_Guru"):
        print(f"📌 GURU: {guru}")
        print("-" * 80)
        
        for _, row in group.iterrows():
            hari = row["Hari"]
            status = row["Status"]
            
            if status == "LIBUR / TIDAK MENGAJAR":
                print(f"  • {hari:<8} : 🟢 LIBUR / TIDAK MENGAJAR")
            else:
                print(f"  • {hari:<8} : 🔴 MENGAJAR ({row['Total_JP']} JP)")
                print(f"    - Kelas & Jam : {row['Detail_Mengajar']}")
                print(f"    - Jam Sela/Gap: {row['Jam_Kosong_Sela']}")
        print()
