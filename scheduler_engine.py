from database import DatabaseLoader
from scheduler_core.solver import SchedulerSolver
from scheduler_core.exporter import ScheduleExporter

class Scheduler:
    def __init__(self, excel_path="database_scheduler.xlsx"):
        self.db_loader = DatabaseLoader(excel_path)
        
    def run(self):
        data = self.db_loader.load_all()
        solver = SchedulerSolver(data)
        
        raw_schedule, unassigned = solver.solve()
        
        # Konversi raw schedule ke DataFrame terstruktur
        df_schedule = ScheduleExporter.to_dataframe(raw_schedule)
        
        return {
            'df_schedule': df_schedule,
            'unassigned': unassigned
        }
