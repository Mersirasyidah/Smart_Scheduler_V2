# scheduler/constraints.py
import pandas as pd

class ConstraintBuilder:
    def __init__(self, solver_class):
        self.s = solver_class
        self.model = solver_class.model
        self.vars = solver_class.vars
        self.idx_mengajar = solver_class.idx_mengajar
        self.idx_slot = solver_class.idx_slot
        self.idx_kelas = solver_class.idx_kelas
        
    def apply_all(self):
        """Menerapkan seluruh aturan penjadwalan ke solver AI CP-SAT"""
        self.rule_one_teacher_one_class_at_a_time()
        self.rule_one_class_one_subject_at_a_time()
        self.rule_teacher_mgmp_dayoff()
        self.rule_total_hours_match_target()
        self.rule_consecutive_hours_pembagian()

    def rule_one_teacher_one_class_at_a_time(self):
        """Aturan: Seorang guru tidak boleh mengajar di dua kelas berbeda pada slot jam yang sama"""
        for t_idx in self.idx_slot:
            for guru_nama in self.s.df_guru:
                baris_mengajar = [
                    m_idx for m_idx, row in self.s.df_mengajar.iterrows()
                    if row["Nama Guru"] == guru_nama
                ]
                if len(baris_mengajar) > 1:
                    self.model.AddAtMostOne(self.vars[(m_idx, t_idx)] for m_idx in baris_mengajar)

    def rule_one_class_one_subject_at_a_time(self):
        """Aturan: Satu kelas hanya boleh diisi oleh maksimal satu sesi mengajar pada satu slot jam"""
        for t_idx in self.idx_slot:
            for kelas in self.s.df_rombel:
                baris_mengajar = [
                    m_idx for m_idx, row in self.s.df_mengajar.iterrows()
                    if row["Kelas"] == kelas
                ]
                self.model.AddAtMostOne(self.vars[(m_idx, t_idx)] for m_idx in baris_mengajar)

    def rule_teacher_mgmp_dayoff(self):
        """Aturan: Guru tidak boleh mengajar di hari libur MGMP mereka"""
        for m_idx, row_m in self.s.df_mengajar.iterrows():
            guru_nama = row_m["Nama Guru"]
            row_g = self.s.df_guru_ref[self.s.df_guru_ref["Nama Guru"] == guru_nama]
            if not row_g.empty:
                hari_mgmp = str(row_g.iloc[0]["Hari MGMP"]).strip()
                if hari_mgmp and hari_mgmp.lower() != 'nan':
                    for t_idx, row_t in self.s.df_slot.iterrows():
                        if str(row_t["Hari"]).lower() == hari_mgmp.lower():
                            self.model.Add(self.vars[(m_idx, t_idx)] == 0)

    def rule_total_hours_match_target(self):
        """Aturan: Jumlah jam mengajar guru di kelas harus sama dengan target JP di database"""
        for m_idx, row in self.s.df_mengajar.iterrows():
            target_jp = int(row["JP"])
            self.model.Add(
                sum(self.vars[(m_idx, t_idx)] for t_idx in self.idx_slot) == target_jp
            )

    def rule_consecutive_hours_pembagian(self):
        """Aturan: Menjaga struktur jam pelajaran berturut-turut berdasarkan kolom Pembagian"""
        for m_idx, row in self.s.df_mengajar.iterrows():
            pembagian_str = str(row.get("Pembagian", "")).strip()
            total_jp = int(row["JP"])
            
            # Pengaman / parser untuk mengantisipasi format tidak biasa (misalnya desimal 2.2 atau 2.1)
            pembagian_str = pembagian_str.replace('.', ',')
            
            try:
                pembagian_target = [int(x.strip()) for x in pembagian_str.split(',') if x.strip().isdigit()]
                if sum(pembagian_target) != total_jp:
                    # Gagal validasi matematika jumlah, gunakan fallback standard
                    pembagian_target = [2, 2, 1] if total_jp == 5 else [total_jp]
            except:
                pembagian_target = [2, 2, 1] if total_jp == 5 else [total_jp]
                
            # Kelompokkan slot berdasarkan Hari
            hari_groups = {}
            for t_idx, row_t in self.s.df_slot.iterrows():
                hari = row_t["Hari"]
                if hari not in hari_groups:
                    hari_groups[hari] = []
                hari_groups[hari].append(t_idx)
                
            # Himpunan jam per hari yang diizinkan (misalnya jika target '2,2,1', maka per hari boleh 0, 1, atau 2 JP)
            valid_jp_per_day = {0} | set(pembagian_target)
            
            for hari, t_indices in hari_groups.items():
                jam_hari_ini = sum(self.vars[(m_idx, t_idx)] for t_idx in t_indices)
                
                temp_vars = []
                for val in valid_jp_per_day:
                    b_var = self.model.NewBoolVar(f'temp_m{m_idx}_{hari}_val{val}')
                    self.model.Add(jam_hari_ini == val).OnlyEnforceIf(b_var)
                    temp_vars.append(b_var)
                self.model.AddExactlyOne(temp_vars)
