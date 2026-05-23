"""
models/pembayaran_model.py
CRUD untuk tabel pembayaran dan bukti transfer.
"""
from models.database import get_db


def get_semua_pembayaran(limit=50):
    conn = get_db()
    rows = conn.execute("""
        SELECT pm.*, p.nama, p.nomor_kamar, t.bulan, t.jumlah as jumlah_tagihan
        FROM pembayaran pm
        JOIN penghuni p  ON pm.penghuni_id = p.id
        JOIN tagihan  t  ON pm.tagihan_id  = t.id
        ORDER BY pm.tanggal_bayar DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def get_pembayaran_by_tagihan(tagihan_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT pm.*, p.nama, p.nomor_kamar
        FROM pembayaran pm
        JOIN penghuni p ON pm.penghuni_id = p.id
        WHERE pm.tagihan_id = ?
        ORDER BY pm.tanggal_bayar DESC
    """, (tagihan_id,)).fetchall()
    conn.close()
    return rows


def get_pembayaran_by_id(pembayaran_id):
    conn = get_db()
    row = conn.execute("""
        SELECT pm.*, p.nama, p.nomor_kamar, t.bulan
        FROM pembayaran pm
        JOIN penghuni p ON pm.penghuni_id = p.id
        JOIN tagihan  t ON pm.tagihan_id  = t.id
        WHERE pm.id = ?
    """, (pembayaran_id,)).fetchone()
    conn.close()
    return row


def tambah_pembayaran(data: dict):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO pembayaran (tagihan_id, penghuni_id, jumlah_bayar, metode, bukti_file, catatan)
        VALUES (:tagihan_id, :penghuni_id, :jumlah_bayar, :metode, :bukti_file, :catatan)
    """, data)
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def verifikasi_pembayaran(pembayaran_id, verified: bool):
    conn = get_db()
    conn.execute(
        "UPDATE pembayaran SET verified=? WHERE id=?",
        (1 if verified else 0, pembayaran_id)
    )
    conn.commit()
    conn.close()


def hapus_pembayaran(pembayaran_id):
    conn = get_db()
    row = conn.execute(
        "SELECT bukti_file FROM pembayaran WHERE id=?", (pembayaran_id,)
    ).fetchone()
    conn.execute("DELETE FROM pembayaran WHERE id=?", (pembayaran_id,))
    conn.commit()
    conn.close()
    return row['bukti_file'] if row else None


def total_dibayar(tagihan_id):
    conn = get_db()
    result = conn.execute(
        "SELECT COALESCE(SUM(jumlah_bayar),0) as total FROM pembayaran WHERE tagihan_id=?",
        (tagihan_id,)
    ).fetchone()
    conn.close()
    return result['total']
