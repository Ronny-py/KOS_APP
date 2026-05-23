"""
models/tagihan_model.py
CRUD untuk tabel tagihan.
"""
from models.database import get_db
import calendar
from datetime import date


def migrate_wa_count():
    """Tambah kolom wa_count ke tabel tagihan jika belum ada."""
    conn = get_db()
    cols = [r['name'] for r in conn.execute("PRAGMA table_info(tagihan)").fetchall()]
    if 'wa_count' not in cols:
        conn.execute("ALTER TABLE tagihan ADD COLUMN wa_count INTEGER DEFAULT 0")
        conn.commit()
    conn.close()


def _default_jatuh_tempo(bulan: str) -> str:
    """Kembalikan tanggal akhir bulan sebagai default jatuh tempo. Format: YYYY-MM-DD"""
    year, month = map(int, bulan.split('-'))
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last_day:02d}"


def get_tagihan_by_penghuni(penghuni_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT t.*, p.nama, p.nomor_kamar
        FROM tagihan t
        JOIN penghuni p ON t.penghuni_id = p.id
        WHERE t.penghuni_id = ?
        ORDER BY t.bulan DESC
    """, (penghuni_id,)).fetchall()
    conn.close()
    return rows


def get_tagihan_by_id(tagihan_id):
    conn = get_db()
    row = conn.execute("""
        SELECT t.*, p.nama, p.nomor_kamar, p.no_hp
        FROM tagihan t
        JOIN penghuni p ON t.penghuni_id = p.id
        WHERE t.id = ?
    """, (tagihan_id,)).fetchone()
    conn.close()
    return row


def get_all_tagihan(status=None, bulan=None):
    conn = get_db()
    query = """
        SELECT t.*, p.nama, p.nomor_kamar
        FROM tagihan t
        JOIN penghuni p ON t.penghuni_id = p.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND t.status = ?"
        params.append(status)
    if bulan:
        query += " AND t.bulan = ?"
        params.append(bulan)
    query += " ORDER BY t.bulan DESC, p.nomor_kamar"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def tambah_tagihan(data: dict):
    # Isi tanggal_jatuh_tempo jika tidak disediakan
    if not data.get('tanggal_jatuh_tempo'):
        data['tanggal_jatuh_tempo'] = _default_jatuh_tempo(data['bulan'])
    conn = get_db()
    conn.execute("""
        INSERT INTO tagihan (penghuni_id, bulan, jumlah, keterangan, status, tanggal_jatuh_tempo)
        VALUES (:penghuni_id, :bulan, :jumlah, :keterangan, 'belum', :tanggal_jatuh_tempo)
    """, data)
    conn.commit()
    conn.close()


def update_status_tagihan(tagihan_id, status):
    conn = get_db()
    conn.execute(
        "UPDATE tagihan SET status=? WHERE id=?", (status, tagihan_id)
    )
    conn.commit()
    conn.close()


def hapus_tagihan(tagihan_id):
    conn = get_db()
    conn.execute("DELETE FROM tagihan WHERE id=?", (tagihan_id,))
    conn.commit()
    conn.close()


def generate_tagihan_bulanan(bulan: str):
    """Buat tagihan otomatis untuk semua penghuni aktif di bulan tertentu."""
    conn = get_db()
    penghuni_list = conn.execute(
        "SELECT id, harga_sewa FROM penghuni WHERE aktif=1"
    ).fetchall()
    jatuh_tempo = _default_jatuh_tempo(bulan)
    count = 0
    for p in penghuni_list:
        existing = conn.execute(
            "SELECT id FROM tagihan WHERE penghuni_id=? AND bulan=?",
            (p['id'], bulan)
        ).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO tagihan (penghuni_id, bulan, jumlah, keterangan, status, tanggal_jatuh_tempo)
                VALUES (?, ?, ?, 'Tagihan sewa bulanan', 'belum', ?)
            """, (p['id'], bulan, p['harga_sewa'], jatuh_tempo))
            count += 1
    conn.commit()
    conn.close()
    return count
