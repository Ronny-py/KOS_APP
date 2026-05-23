"""
set_admin_expiry.py
────────────────────────────────────────────────────────────────────
Script satu kali jalan untuk:
  1. Menambah kolom last_seen, max_date_seen, expiry_token (kalau belum ada)
  2. Men-generate expiry_token (HMAC) untuk admin yang sudah ada di DB
  3. Menampilkan ringkasan

Jalankan SATU KALI dari root project:
    python set_admin_expiry.py
────────────────────────────────────────────────────────────────────
"""
import sqlite3
import sys
import os
from datetime import date, timedelta

# Pastikan import config & license_guard bisa jalan dari root project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATABASE
from utils.license_guard import buat_token

TAMBAH_HARI = 30   # ← ubah sesuai kebutuhan


def run():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    # ── 1. Tambah kolom yang belum ada ───────────────────────────────────────
    cur.execute("PRAGMA table_info(admin)")
    existing = {row["name"] for row in cur.fetchall()}

    for col, ddl in {
        "last_seen":     "ALTER TABLE admin ADD COLUMN last_seen      TEXT",
        "max_date_seen": "ALTER TABLE admin ADD COLUMN max_date_seen  TEXT",
        "expiry_token":  "ALTER TABLE admin ADD COLUMN expiry_token   TEXT",
    }.items():
        if col not in existing:
            cur.execute(ddl)
            print(f"  [+] Kolom '{col}' ditambahkan.")

    conn.commit()

    # ── 2. Buat / perbarui token untuk semua admin ───────────────────────────
    cur.execute("SELECT id, username, expired_at FROM admin")
    admins = cur.fetchall()

    for admin in admins:
        admin_id   = admin["id"]
        username   = admin["username"]
        expired_at = admin["expired_at"]

        # Kalau belum ada expired_at, set dari sekarang + TAMBAH_HARI
        if not expired_at:
            expired_at = (date.today() + timedelta(days=TAMBAH_HARI)).isoformat()
            print(f"  [admin:{username}] expired_at kosong → diset ke {expired_at}")

        token = buat_token(admin_id, expired_at)

        cur.execute(
            "UPDATE admin SET expired_at = ?, expiry_token = ? WHERE id = ?",
            (expired_at, token, admin_id)
        )
        print(f"  [admin:{username}] expired_at={expired_at}  token={token[:20]}...")

    conn.commit()
    conn.close()

    print("\n✅ Selesai. Jalankan aplikasi seperti biasa.")
    print("   Kolom last_seen & max_date_seen akan terisi otomatis saat login pertama.\n")


if __name__ == "__main__":
    run()
