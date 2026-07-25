from database import DatabaseLoader
from scheduler_core.solver import SchedulerSolver
from scheduler_core.exporter import ScheduleExporter

class Scheduler:  # <-- Gunakan nama 'Scheduler' agar cocok dengan import di pages
    def __init__(self, excel_path="database_scheduler.xlsx"):
        self.db_loader = DatabaseLoader(excel_path)
        
    def run(self):
        data = self.db_loader.load_all()
        solver = SchedulerSolver(data)
        
        raw_schedule, unassigned = solver.solve()
        
        df_schedule = ScheduleExporter.to_dataframe(raw_schedule)
        class_matrix = ScheduleExporter.create_class_matrix(df_schedule)
        
        return {
            'df_schedule': df_schedule,
            'class_matrix': class_matrix,
            'unassigned': unassigned
        }
