# --- DI DALAM FUNGSI generate_schedule_kelas_7 ---

# 1. Pastikan Struktur Blok IPA Mutlak 2 + 2 + 1
if 'ipa' in m_lower or 'ilmu pengetahuan alam' in m_lower:
    blocks = [2, 2, 1]  # Strict 2 JP, 2 JP, 1 JP

# 2. Urutan Prioritas Plotting (IPA Ditaruh di Paling Atas bersama PAI 7A & PJOK)
def priority_key(group):
    m = group['mapel'].lower()
    k = group['kelas']
    
    # Priority 0: PAI 7A (Sesuai Aturan Kunci)
    if ('agama' in m or 'pai' in m) and k == '7A': 
        return (0, 0)
    
    # Priority 1: IPA (G33) - Ditaruh di Paling Depan Agar Slot 2+2+1 Bebas Memilih
    if 'ipa' in m or 'ilmu pengetahuan alam' in m: 
        return (1, 0)
    
    # Priority 2: PJOK (Butuh Lapangan/Jam Pagi)
    if 'pjok' in m or 'jasmani' in m: 
        return (2, 0)
    
    # Priority 3: PAI Kelas Lain
    if 'agama' in m or 'pai' in m: 
        return (3, 0)
    
    # Priority 4: Mapel Lainnya Berdasarkan Beban Guru
    return (4, -group['workload'])

assignment_groups.sort(key=priority_key)
