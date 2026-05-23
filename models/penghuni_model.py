"""
models/penghuni_model.py
CRUD untuk tabel penghuni.
"""
from models.database import get_db


def get_all_penghuni(aktif_only=False):
    conn = get_db()
    if aktif_only:
        rows = conn.execute(
            "SELECT * FROM penghuni WHERE aktif=1 ORDER BY nomor_kamar"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM penghuni ORDER BY aktif DESC, nomor_kamar"
        ).fetchall()
    conn.close()
    return rows


def get_penghuni_by_id(penghuni_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM penghuni WHERE id=?", (penghuni_id,)
    ).fetchone()
    conn.close()
    return row


def tambah_penghuni(data: dict):
    conn = get_db()
    conn.execute("""
        INSERT INTO penghuni (nama, nomor_kamar, no_hp, email, tanggal_masuk, harga_sewa)
        VALUES (:nama, :nomor_kamar, :no_hp, :email, :tanggal_masuk, :harga_sewa)
    """, data)
    last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return last_id


def update_penghuni(penghuni_id, data: dict):
    data['id'] = penghuni_id
    conn = get_db()
    conn.execute("""
        UPDATE penghuni
        SET nama=:nama, nomor_kamar=:nomor_kamar, no_hp=:no_hp,
            email=:email, tanggal_masuk=:tanggal_masuk, harga_sewa=:harga_sewa
        WHERE id=:id
    """, data)
    conn.commit()
    conn.close()


def update_dokumen_penghuni(penghuni_id, field: str, filename: str):
    """Update satu kolom dokumen (foto_ktp / bukti_transfer_jaminan / bukti_pengembalian_jaminan)."""
    allowed = {'foto_ktp', 'bukti_transfer_jaminan', 'bukti_pengembalian_jaminan'}
    if field not in allowed:
        raise ValueError(f"Field tidak diizinkan: {field}")
    conn = get_db()
    conn.execute(f"UPDATE penghuni SET {field}=? WHERE id=?", (filename, penghuni_id))
    conn.commit()
    conn.close()


def hapus_dokumen_penghuni(penghuni_id, field: str):
    """Hapus referensi dokumen (set NULL)."""
    allowed = {'foto_ktp', 'bukti_transfer_jaminan', 'bukti_pengembalian_jaminan'}
    if field not in allowed:
        raise ValueError(f"Field tidak diizinkan: {field}")
    conn = get_db()
    conn.execute(f"UPDATE penghuni SET {field}=NULL WHERE id=?", (penghuni_id,))
    conn.commit()
    conn.close()


def nonaktifkan_penghuni(penghuni_id):
    conn = get_db()
    conn.execute("UPDATE penghuni SET aktif=0 WHERE id=?", (penghuni_id,))
    conn.commit()
    conn.close()


def hapus_penghuni(penghuni_id):
    conn = get_db()
    conn.execute("DELETE FROM penghuni WHERE id=?", (penghuni_id,))
    conn.commit()
    conn.close()
