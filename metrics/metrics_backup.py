import shutil
import os
from datetime import datetime

def backup_metrics_db(db_path='metrics/chess_metrics.db', backup_dir='metrics/backups'):
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'chess_metrics_{timestamp}.db')
    shutil.copy2(db_path, backup_path)
    return backup_path
