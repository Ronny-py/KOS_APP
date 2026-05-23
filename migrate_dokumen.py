"""
utils/migrate_dokumen.py
Jalankan fungsi ini saat aplikasi start untuk memastikan
kolom dokumen penghuni sudah ada di database.

Cara pakai di app.py:
    from utils.migrate_dokumen import migrate_dokumen_penghuni
    with app.app_context():
        migrate_dokumen_penghuni()
"""
from models.database import get_db


def migrate_dokumen_penghuni():
    """
    Tambah kolom foto_ktp, bukti_transfer_jaminan, bukti_pengembalian_jaminan
    ke tabel penghuni jika belum ada. Aman dijalankan berkali-kali.
    """
    conn = get_db()

    # Cek kolom yang sudah ada
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(penghuni)").fetchall()
    }

    kolom_baru = [
        ("foto_ktp",                   "TEXT DEFAULT NULL"),
        ("bukti_transfer_jaminan",     "TEXT DEFAULT NULL"),
        ("bukti_pengembalian_jaminan", "TEXT DEFAULT NULL"),
    ]

    for nama_kolom, definisi in kolom_baru:
        if nama_kolom not in existing:
            conn.execute(f"ALTER TABLE penghuni ADD COLUMN {nama_kolom} {definisi}")
            print(f"[migrate] Kolom '{nama_kolom}' ditambahkan ke tabel penghuni.")
        else:
            print(f"[migrate] Kolom '{nama_kolom}' sudah ada, dilewati.")

    conn.commit()
    conn.close()
