"""
utils/migrate_pengeluaran.py
Tambah tabel pengeluaran jika belum ada.
Dipanggil dari app.py saat startup.
"""
from models.database import get_db


def migrate_pengeluaran():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS pengeluaran (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal    TEXT    NOT NULL,          -- format: YYYY-MM-DD
            kategori   TEXT,                      -- Listrik, Air, Kebersihan, dll.
            keterangan TEXT,
            jumlah     REAL    NOT NULL DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    db.commit()
    db.close()
    print("[DB] Tabel pengeluaran siap.")
