from dataclasses import dataclass
from typing import Dict, List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


# ==========================================
# 1. STRUKTUR DATA INPUT
# ==========================================
@dataclass
class Teacher:
  code: str
  name: str
  status: str  # 'GTT' atau 'PERMANENT'
  mgmp_day: str  # 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat'


@dataclass
class SubjectAssignment:
  class_name: str  # e.g., '9A'
  subject_code: str  # e.g., 'M08', 'M09', 'M11'
  teacher_code: str
  hours: int  # Total JP per minggu
  priority: int  # 1 = Tertinggi


# Contoh Input Data Guru & MGMP
teachers_data = {
    'G01': Teacher('G01', 'Purwanto, S.Pd.', 'PERMANENT', 'Selasa'),
    'G02': Teacher('G02', 'Asti Am Rini, S.Pd.', 'PERMANENT', 'Rabu'),
    'G03': Teacher('G03', 'Luthfan Qaedi W.', 'GTT', 'Kamis'),
    'G04': Teacher('G04', 'Anggi Supriyadi, S.Hum', 'GTT', 'Jumat'),
    # Tambahkan seluruh data guru Anda di sini...
}

# Contoh Input Alokasi Mapel & Jam Mengajar Kelas
assignments_data = [
    # Kelas 9A
    SubjectAssignment('9A', 'M08', 'G01', 4, priority=1),
    SubjectAssignment('9A', 'M09', 'G02', 4, priority=2),
    SubjectAssignment('9A', 'M11', 'G03', 5, priority=3),
    # Kelas 8A
    SubjectAssignment('8A', 'M08', 'G01', 4, priority=1),
    SubjectAssignment('8A', 'M11', 'G04', 5, priority=3),
    # Tambahkan assignment kelas lainnya di sini...
]

DAYS = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat']
PERIODS_PER_DAY = {'Senin': 9, 'Selasa': 9, 'Rabu': 9, 'Kamis': 9, 'Jumat': 6}


# ==========================================
# 2. VALIDATOR CONSTRAINT (CEK ATURAN)
# ==========================================
class ScheduleSolver:

  def __init__(self, teachers: Dict[str, Teacher], assignments: List[SubjectAssignment]):
    self.teachers = teachers
    self.assignments = assignments
    self.schedule = {}  # (class_name, day, period) -> assignment
    self.teacher_daily_hours = {}  # (teacher_code, day) -> count

  def can_place(
      self, assign: SubjectAssignment, day: str, period: int
  ) -> bool:
    teacher = self.teachers.get(assign.teacher_code)

    # 1. Cek Bentrok Guru di Jam dan Hari yang sama
    for (c, d, p), a in self.schedule.items():
      if d == day and p == period and a.teacher_code == assign.teacher_code:
        return False  # Guru sedang mengajar di kelas lain

    # 2. Aturan Hari MGMP
    if teacher and teacher.mgmp_day == day:
      if teacher.status == 'GTT':
        return False  # GTT Libur total saat hari MGMP
      elif teacher.status == 'PERMANENT' and period > 3:
        return False  # Non-GTT Maksimal mengajar s.d. Jam ke-3

    # 3. Aturan Maksimal 6 JP per Hari per Guru
    current_teacher_hours = self.teacher_daily_hours.get(
        (assign.teacher_code, day), 0
    )
    if current_teacher_hours >= 6:
      return False

    # 4. Aturan Mapel M11
    if assign.subject_code == 'M11':
      if day == 'Senin':
        # Diprioritaskan jam 2-4, sisa maksimal jam 6
        if period < 2 or period > 6:
          return False
      else:
        # Diprioritaskan jam 1-3, sisa maksimal jam 6
        if period > 6:
          return False

    # 5. Aturan Pagi untuk M08 & M09
    if assign.subject_code in ['M08', 'M09']:
      if period > 4:  # Wajib Pagi (Maksimal Jam ke-4)
        return False

    # 6. Aturan Khusus Kelas 9: M08 dan M09 Sebelum M11
    if assign.class_name.startswith('9') and assign.subject_code == 'M11':
      # Cek apakah M08 dan M09 sudah ditaruh di jam sebelumnya pada hari/minggu tersebut
      m08_placed = any(
          a.subject_code == 'M08'
          for (c, d, p), a in self.schedule.items()
          if c == assign.class_name
      )
      if not m08_placed:
        return False  # M08 harus masuk dulu sebelum M11 dipasang

    return True

  def solve(self) -> bool:
    # Sortir assignment berdasarkan prioritas
    sorted_assignments = sorted(self.assignments, key=lambda x: x.priority)

    # Algoritma penempatan jadwal
    for assign in sorted_assignments:
      hours_left = assign.hours
      for day in DAYS:
        for p in range(1, PERIODS_PER_DAY[day] + 1):
          if hours_left == 0:
            break

          # Cek slot kosong di kelas tersebut
          if (assign.class_name, day, p) in self.schedule:
            continue

          if self.can_place(assign, day, p):
            # Place
            self.schedule[(assign.class_name, day, p)] = assign
            self.teacher_daily_hours[(assign.teacher_code, day)] = (
                self.teacher_daily_hours.get((assign.teacher_code, day), 0) + 1
            )
            hours_left -= 1

    return True


# ==========================================
# 3. JALANKAN GENERATOR
# ==========================================
solver = ScheduleSolver(teachers_data, assignments_data)
if solver.solve():
  print("✅ Jadwal berhasil dibuat secara otomatis sesuai aturan!")
else:
  print("❌ Ada bentrok atau aturan yang gagal dipenuhi.")
