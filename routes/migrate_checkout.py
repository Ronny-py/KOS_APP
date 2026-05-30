"""
utils/migrate_checkout.py
Buat tabel checkout jika belum ada.
"""
from models.database import get_db


def migrate_checkout():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS checkout (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            penghuni_id             INTEGER NOT NULL,
            nama                    TEXT NOT NULL,
            nomor_kamar             TEXT NOT NULL,
            tanggal_masuk           TEXT,
            tanggal_keluar          TEXT NOT NULL,
            lama_tinggal_hari       INTEGER,
            harga_sewa              REAL DEFAULT 0,
            deposit_awal            REAL DEFAULT 0,
            tagihan_belum_lunas     REAL DEFAULT 0,
            potongan_kerusakan      REAL DEFAULT 0,
            keterangan_potongan     TEXT,
            deposit_dikembalikan    REAL DEFAULT 0,
            kondisi_kamar           TEXT DEFAULT 'baik',
            catatan                 TEXT,
            bukti_pengembalian      TEXT,
            processed_by            TEXT,
            created_at              TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (penghuni_id) REFERENCES penghuni(id)
        )
    """)

    # Tambah kolom tanggal_keluar & deposit ke penghuni jika belum ada
    cols = [r[1] for r in db.execute("PRAGMA table_info(penghuni)").fetchall()]
    if 'tanggal_keluar' not in cols:
        db.execute("ALTER TABLE penghuni ADD COLUMN tanggal_keluar TEXT")
    if 'deposit' not in cols:
        db.execute("ALTER TABLE penghuni ADD COLUMN deposit REAL DEFAULT 0")

    db.commit()
