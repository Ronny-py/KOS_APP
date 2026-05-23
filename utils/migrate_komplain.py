"""
utils/migrate_komplain.py
Membuat tabel komplain jika belum ada.
Jalankan sekali saat app start (dipanggil dari create_app).
"""
from models.database import get_db


def migrate_komplain():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS komplain (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_pelapor  TEXT    NOT NULL,
            nomor_kamar   TEXT    NOT NULL,
            no_hp         TEXT,
            kategori      TEXT    NOT NULL DEFAULT 'lainnya',
            judul         TEXT    NOT NULL,
            deskripsi     TEXT    NOT NULL,
            foto_path     TEXT,
            status        TEXT    NOT NULL DEFAULT 'baru',
            -- status: baru | diproses | selesai | ditolak
            prioritas     TEXT    NOT NULL DEFAULT 'normal',
            -- prioritas: rendah | normal | tinggi | urgent
            catatan_admin TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            selesai_at    TEXT
        )
    """)
    db.commit()
