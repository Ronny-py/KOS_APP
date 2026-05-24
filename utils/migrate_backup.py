"""
utils/migrate_backup.py
Inisialisasi folder backups/ jika belum ada.
"""
import os

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backups')


def migrate_backup():
    """Buat folder backups/ jika belum ada."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    # Tambahkan .gitignore agar file backup tidak ikut ter-commit
    gitignore = os.path.join(BACKUP_DIR, '.gitignore')
    if not os.path.exists(gitignore):
        with open(gitignore, 'w') as f:
            f.write('# Jangan commit file backup database\n*.db\n*.sql\n')
