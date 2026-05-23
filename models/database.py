"""
models/database.py
Koneksi database SQLite dan helper query.
"""
import sqlite3
from config import DATABASE


def get_db():
    """Buka koneksi ke database SQLite."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # akses kolom via nama
    return conn


def init_db():
    """Buat semua tabel jika belum ada."""
    conn = get_db()
    cur = conn.cursor()

    # Tabel penghuni kost
    cur.execute("""
        CREATE TABLE IF NOT EXISTS penghuni (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nama        TEXT    NOT NULL,
            nomor_kamar TEXT    NOT NULL UNIQUE,
            no_hp       TEXT,
            email       TEXT,
            tanggal_masuk TEXT,
            harga_sewa  REAL    NOT NULL DEFAULT 0,
            aktif       INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # Tabel tagihan
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tagihan (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            penghuni_id         INTEGER NOT NULL,
            bulan               TEXT    NOT NULL,   -- format: YYYY-MM
            jumlah              REAL    NOT NULL,
            keterangan          TEXT,
            status              TEXT    NOT NULL DEFAULT 'belum',  -- belum / lunas / sebagian
            tanggal_jatuh_tempo TEXT,
            notif_wa_terkirim   INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (penghuni_id) REFERENCES penghuni(id)
        )
    """)

    # Tabel bukti transfer / pembayaran
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pembayaran (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tagihan_id   INTEGER NOT NULL,
            penghuni_id  INTEGER NOT NULL,
            jumlah_bayar REAL    NOT NULL,
            metode       TEXT    NOT NULL DEFAULT 'transfer',
            bukti_file   TEXT,               -- path file upload
            catatan      TEXT,
            tanggal_bayar TEXT   DEFAULT (datetime('now','localtime')),
            verified     INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (tagihan_id)  REFERENCES tagihan(id),
            FOREIGN KEY (penghuni_id) REFERENCES penghuni(id)
        )
    """)

    # Tabel admin / user login
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL,
            nama     TEXT
        )
    """)

    # Seed admin default (password: admin123)
    from werkzeug.security import generate_password_hash
    cur.execute("SELECT id FROM admin WHERE username='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO admin (username, password, nama) VALUES (?,?,?)",
            ('admin', generate_password_hash('admin123'), 'Administrator')
        )

    conn.commit()

    # ── Migrasi otomatis kolom baru ──────────────────────────────────────────
    _migrate(conn)

    conn.close()
    print("[DB] Database diinisialisasi.")


def _migrate(conn):
    """
    Tambah kolom baru ke tabel yang sudah ada (idempoten — aman dijalankan berulang).
    """
    existing_tagihan = {
        row[1] for row in conn.execute("PRAGMA table_info(tagihan)").fetchall()
    }

    # Kolom tanggal_jatuh_tempo (mungkin belum ada di DB lama)
    if "tanggal_jatuh_tempo" not in existing_tagihan:
        conn.execute("ALTER TABLE tagihan ADD COLUMN tanggal_jatuh_tempo TEXT")
        print("[DB] Migrasi: kolom tanggal_jatuh_tempo ditambahkan ke tagihan")

    # Kolom notif_wa_terkirim (untuk fitur notifikasi WA)
    if "notif_wa_terkirim" not in existing_tagihan:
        conn.execute(
            "ALTER TABLE tagihan ADD COLUMN notif_wa_terkirim INTEGER NOT NULL DEFAULT 0"
        )
        print("[DB] Migrasi: kolom notif_wa_terkirim ditambahkan ke tagihan")

    conn.commit()
