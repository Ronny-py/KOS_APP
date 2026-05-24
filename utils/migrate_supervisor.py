"""
utils/migrate_supervisor.py
Buat tabel supervisor dan activity_log jika belum ada.
"""
from models.database import get_db


def migrate_supervisor():
    db = get_db()

    # ── Tabel akun supervisor ──────────────────────────────────────────────
    db.execute("""
        CREATE TABLE IF NOT EXISTS supervisor (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    NOT NULL UNIQUE,
            password   TEXT    NOT NULL,
            nama       TEXT,
            aktif      INTEGER NOT NULL DEFAULT 1,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Tabel log login admin ──────────────────────────────────────────────
    db.execute("""
        CREATE TABLE IF NOT EXISTS login_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER,
            username   TEXT    NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            city       TEXT,
            region     TEXT,
            country    TEXT,
            latitude   TEXT,
            longitude  TEXT,
            status     TEXT    NOT NULL DEFAULT 'success',   -- success / failed
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (admin_id) REFERENCES admin(id)
        )
    """)

    # ── Tabel log akses menu/halaman ──────────────────────────────────────
    db.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER,
            username   TEXT    NOT NULL,
            endpoint   TEXT,
            menu_label TEXT,
            method     TEXT,
            ip_address TEXT,
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (admin_id) REFERENCES admin(id)
        )
    """)

    # Sisipkan akun supervisor default jika tabel masih kosong
    existing = db.execute("SELECT COUNT(*) FROM supervisor").fetchone()[0]
    if existing == 0:
        import hashlib
        pw_hash = hashlib.sha256("supervisor123".encode()).hexdigest()
        db.execute(
            "INSERT INTO supervisor (username, password, nama) VALUES (?, ?, ?)",
            ("supervisor", pw_hash, "Supervisor")
        )

    db.commit()
    print("[migrate_supervisor] ✅ Tabel supervisor, login_log, activity_log siap.")
