"""
utils/migrate_notif_wa.py
Migration untuk tabel notifikasi WhatsApp.
"""

def migrate_notif_wa():
    """
    Jalankan migration untuk tabel notif_wa (jika diperlukan).
    Fungsi ini dipanggil saat aplikasi startup di app.py
    """
    from models.database import get_db
    
    try:
        conn = get_db()
        
        # Cek apakah tabel notif_wa sudah ada
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notif_wa'"
        ).fetchone()
        
        if not tables:
            # Buat tabel notif_wa jika belum ada
            conn.execute("""
                CREATE TABLE notif_wa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    penghuni_id INTEGER NOT NULL,
                    pesan TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',  -- pending, sent, failed
                    tanggal_kirim TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tanggal_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_msg TEXT,
                    FOREIGN KEY (penghuni_id) REFERENCES penghuni(id)
                )
            """)
            conn.commit()
            print("✓ Tabel notif_wa berhasil dibuat")
        
        conn.close()
    except Exception as e:
        print(f"⚠ Warning saat migration notif_wa: {e}")
