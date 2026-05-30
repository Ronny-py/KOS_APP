"""
utils/migrate_keterangan.py
Tambah kolom 'keterangan' ke tabel pembayaran (jika belum ada).
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'kost.db')


def migrate_keterangan():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    # Cek apakah kolom sudah ada
    cur.execute("PRAGMA table_info(pembayaran)")
    cols = [row[1] for row in cur.fetchall()]
    if 'keterangan' not in cols:
        cur.execute("ALTER TABLE pembayaran ADD COLUMN keterangan TEXT DEFAULT ''")
        conn.commit()
        print("[migrate_keterangan] Kolom 'keterangan' berhasil ditambahkan.")
    else:
        print("[migrate_keterangan] Kolom 'keterangan' sudah ada, skip.")
    conn.close()
