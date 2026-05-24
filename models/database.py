"""
models/database.py  (VERSI SUPERVISOR)
Koneksi database SQLite dan helper query.
Tambahan: tabel supervisor, log_login_supervisor, log_aktivitas.
"""
import sqlite3
from config import DATABASE


def get_db():
    """Buka koneksi ke database SQLite."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Buat semua tabel jika belum ada."""
    conn = get_db()
    cur  = conn.cursor()

    # ── Tabel penghuni kost ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS penghuni (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nama          TEXT    NOT NULL,
            nomor_kamar   TEXT    NOT NULL UNIQUE,
            no_hp         TEXT,
            email         TEXT,
            tanggal_masuk TEXT,
            harga_sewa    REAL    NOT NULL DEFAULT 0,
            aktif         INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Tabel tagihan ────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tagihan (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            penghuni_id         INTEGER NOT NULL,
            bulan               TEXT    NOT NULL,
            jumlah              REAL    NOT NULL,
            keterangan          TEXT,
            status              TEXT    NOT NULL DEFAULT 'belum',
            tanggal_jatuh_tempo TEXT,
            notif_wa_terkirim   INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (penghuni_id) REFERENCES penghuni(id)
        )
    """)

    # ── Tabel pembayaran ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pembayaran (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tagihan_id   INTEGER NOT NULL,
            penghuni_id  INTEGER NOT NULL,
            jumlah_bayar REAL    NOT NULL,
            metode       TEXT    NOT NULL DEFAULT 'transfer',
            bukti_file   TEXT,
            catatan      TEXT,
            tanggal_bayar TEXT   DEFAULT (datetime('now','localtime')),
            verified     INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (tagihan_id)  REFERENCES tagihan(id),
            FOREIGN KEY (penghuni_id) REFERENCES penghuni(id)
        )
    """)

    # ── Tabel admin ──────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL,
            nama     TEXT
        )
    """)

    # ── Tabel supervisor ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS supervisor (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password      TEXT    NOT NULL,
            nama          TEXT    NOT NULL,
            aktif         INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Tabel log login supervisor ───────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS log_login_supervisor (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER,
            username      TEXT    NOT NULL,
            berhasil      INTEGER NOT NULL DEFAULT 0,   -- 1=berhasil, 0=gagal
            ip            TEXT,
            waktu         TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Tabel log login admin ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS log_login_admin (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            username TEXT    NOT NULL,
            berhasil INTEGER NOT NULL DEFAULT 0,
            ip       TEXT,
            waktu    TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Tabel log aktivitas menu ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS log_aktivitas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER,
            admin_nama TEXT,
            menu       TEXT    NOT NULL,   -- nama modul, mis: 'Penghuni', 'Tagihan'
            aksi       TEXT    NOT NULL,   -- mis: 'Tambah', 'Edit', 'Hapus'
            keterangan TEXT,               -- detail bebas
            ip         TEXT,
            waktu      TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Seed admin default (password: admin123) ──────────────────────────────
    from werkzeug.security import generate_password_hash
    cur.execute("SELECT id FROM admin WHERE username='admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO admin (username, password, nama) VALUES (?,?,?)",
            ('admin', generate_password_hash('admin123'), 'Administrator')
        )

    # ── Seed supervisor default (password: supervisor123) ────────────────────
    cur.execute("SELECT id FROM supervisor WHERE username='supervisor'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO supervisor (username, password, nama) VALUES (?,?,?)",
            ('supervisor', generate_password_hash('supervisor123'), 'Supervisor Utama')
        )

    conn.commit()
    _migrate(conn)
    conn.close()
    print("[DB] Database diinisialisasi.")


def _migrate(conn):
    """
    Tambah kolom baru ke tabel yang sudah ada (idempoten — aman dijalankan berulang).
    """
    # ── Migrasi tabel tagihan ────────────────────────────────────────────────
    tagihan_cols = {r[1] for r in conn.execute("PRAGMA table_info(tagihan)").fetchall()}
    if "tanggal_jatuh_tempo" not in tagihan_cols:
        conn.execute("ALTER TABLE tagihan ADD COLUMN tanggal_jatuh_tempo TEXT")
        print("[DB] Migrasi: kolom tanggal_jatuh_tempo ditambahkan ke tagihan")
    if "notif_wa_terkirim" not in tagihan_cols:
        conn.execute("ALTER TABLE tagihan ADD COLUMN notif_wa_terkirim INTEGER NOT NULL DEFAULT 0")
        print("[DB] Migrasi: kolom notif_wa_terkirim ditambahkan ke tagihan")

    # ── Pastikan tabel supervisor & log sudah ada (untuk DB lama) ────────────
    _ensure_supervisor_tables(conn)

    conn.commit()


def _ensure_supervisor_tables(conn):
    """Buat tabel supervisor & log jika belum ada (untuk DB yang sudah jalan sebelum fitur ini)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supervisor (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    NOT NULL UNIQUE,
            password   TEXT    NOT NULL,
            nama       TEXT    NOT NULL,
            aktif      INTEGER NOT NULL DEFAULT 1,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_login_supervisor (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER,
            username      TEXT    NOT NULL,
            berhasil      INTEGER NOT NULL DEFAULT 0,
            ip            TEXT,
            waktu         TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_login_admin (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            username TEXT    NOT NULL,
            berhasil INTEGER NOT NULL DEFAULT 0,
            ip       TEXT,
            waktu    TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_aktivitas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER,
            admin_nama TEXT,
            menu       TEXT NOT NULL,
            aksi       TEXT NOT NULL,
            keterangan TEXT,
            ip         TEXT,
            waktu      TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    # Seed supervisor default jika belum ada
    from werkzeug.security import generate_password_hash
    sv = conn.execute("SELECT id FROM supervisor WHERE username='supervisor'").fetchone()
    if not sv:
        conn.execute(
            "INSERT INTO supervisor (username, password, nama) VALUES (?,?,?)",
            ('supervisor', generate_password_hash('supervisor123'), 'Supervisor Utama')
        )


# ── Helper: catat log aktivitas (pakai di route admin) ───────────────────────
def catat_aktivitas(admin_id, admin_nama: str, menu: str, aksi: str,
                    keterangan: str = None, ip: str = None):
    """
    Panggil ini di setiap route admin saat ada perubahan data.
    Contoh:
        from models.database import catat_aktivitas
        catat_aktivitas(session['admin_id'], session['admin_nama'],
                        'Penghuni', 'Tambah', f'Kamar {nomor_kamar}',
                        request.remote_addr)
    """
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO log_aktivitas (admin_id, admin_nama, menu, aksi, keterangan, ip)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (admin_id, admin_nama, menu, aksi, keterangan, ip))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOG] Gagal catat aktivitas: {e}")
