"""
utils/migrate_admin_expiry.py
Migrasi tabel admin:
  - expired_at      : tanggal kadaluarsa akun
  - last_seen       : timestamp login terakhir (untuk deteksi jam dimundurkan)
  - max_date_seen   : tanggal terbesar yang pernah dicapai (anti-rollback)
  - expiry_token    : HMAC signature agar expired_at tidak bisa diedit manual di DB
"""
from models.database import get_db


def migrate_admin_expiry():
    db = get_db()
    cur = db.cursor()

    # Ambil kolom yang sudah ada
    cur.execute("PRAGMA table_info(admin)")
    existing = {row[1] for row in cur.fetchall()}

    alterations = {
        "expired_at":    "ALTER TABLE admin ADD COLUMN expired_at    TEXT",
        "last_seen":     "ALTER TABLE admin ADD COLUMN last_seen      TEXT",
        "max_date_seen": "ALTER TABLE admin ADD COLUMN max_date_seen  TEXT",
        "expiry_token":  "ALTER TABLE admin ADD COLUMN expiry_token   TEXT",
    }

    for col, sql in alterations.items():
        if col not in existing:
            cur.execute(sql)
            print(f"[migrate_admin_expiry] kolom '{col}' ditambahkan.")

    db.commit()
