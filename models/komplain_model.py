"""
models/komplain_model.py
CRUD untuk tabel komplain.
"""
from models.database import get_db


# ── Kategori & Prioritas ──────────────────────────────────────────────────────
KATEGORI_LIST = [
    ('listrik',    '⚡ Listrik / Kelistrikan'),
    ('air',        '🚿 Air / Plumbing'),
    ('ac',         '❄️ AC / Kipas'),
    ('internet',   '📶 Internet / WiFi'),
    ('pintu_kunci','🔐 Pintu / Kunci / Gembok'),
    ('kebersihan', '🧹 Kebersihan'),
    ('keamanan',   '🔒 Keamanan'),
    ('furnitur',   '🪑 Furnitur / Perabot'),
    ('lainnya',    '📝 Lainnya'),
]

PRIORITAS_LIST = [
    ('rendah',  '🟢 Rendah'),
    ('normal',  '🔵 Normal'),
    ('tinggi',  '🟠 Tinggi'),
    ('urgent',  '🔴 Urgent'),
]

STATUS_LIST = [
    ('baru',      '🆕 Baru'),
    ('diproses',  '🔧 Diproses'),
    ('selesai',   '✅ Selesai'),
    ('ditolak',   '❌ Ditolak'),
]


def get_all(status=None, bulan=None, tahun=None, search=None):
    db   = get_db()
    sql  = "SELECT * FROM komplain WHERE 1=1"
    args = []
    if status:
        sql += " AND status = ?"; args.append(status)
    if bulan and tahun:
        sql += " AND strftime('%Y-%m', created_at) = ?"; args.append(f"{tahun}-{bulan:02d}")
    if search:
        sql += " AND (nama_pelapor LIKE ? OR nomor_kamar LIKE ? OR judul LIKE ?)"; args += [f"%{search}%"]*3
    sql += " ORDER BY created_at DESC"
    return db.execute(sql, args).fetchall()


def get_by_id(kid):
    return get_db().execute("SELECT * FROM komplain WHERE id=?", (kid,)).fetchone()


def tambah(nama, kamar, no_hp, kategori, judul, deskripsi, foto_path=None, prioritas='normal'):
    db = get_db()
    db.execute("""
        INSERT INTO komplain (nama_pelapor,nomor_kamar,no_hp,kategori,judul,deskripsi,foto_path,prioritas)
        VALUES (?,?,?,?,?,?,?,?)
    """, (nama, kamar, no_hp, kategori, judul, deskripsi, foto_path, prioritas))
    db.commit()


def update_status(kid, status, catatan_admin=None):
    db = get_db()
    selesai_at = "datetime('now','localtime')" if status in ('selesai','ditolak') else "NULL"
    db.execute(f"""
        UPDATE komplain
        SET status=?, catatan_admin=?, updated_at=datetime('now','localtime'),
            selesai_at=({selesai_at})
        WHERE id=?
    """, (status, catatan_admin, kid))
    db.commit()


def update_prioritas(kid, prioritas):
    db = get_db()
    db.execute("UPDATE komplain SET prioritas=?, updated_at=datetime('now','localtime') WHERE id=?",
               (prioritas, kid))
    db.commit()


def hapus(kid):
    db = get_db()
    row = db.execute("SELECT foto_path FROM komplain WHERE id=?", (kid,)).fetchone()
    db.execute("DELETE FROM komplain WHERE id=?", (kid,))
    db.commit()
    return row['foto_path'] if row else None


# ── Stats untuk dashboard / laporan ──────────────────────────────────────────
def stats_bulan(bulan, tahun):
    db  = get_db()
    ym  = f"{tahun}-{bulan:02d}"
    row = db.execute("""
        SELECT
            COUNT(*) total,
            SUM(status='baru')     baru,
            SUM(status='diproses') diproses,
            SUM(status='selesai')  selesai,
            SUM(status='ditolak')  ditolak,
            SUM(prioritas='urgent') urgent
        FROM komplain
        WHERE strftime('%Y-%m', created_at)=?
    """, (ym,)).fetchone()
    return row


def stats_per_kategori(bulan=None, tahun=None):
    db  = get_db()
    sql = "SELECT kategori, COUNT(*) jumlah FROM komplain"
    args = []
    if bulan and tahun:
        sql += " WHERE strftime('%Y-%m', created_at)=?"; args.append(f"{tahun}-{bulan:02d}")
    sql += " GROUP BY kategori ORDER BY jumlah DESC"
    return db.execute(sql, args).fetchall()


def avg_selesai_hari(bulan=None, tahun=None):
    db  = get_db()
    sql = """
        SELECT AVG((julianday(selesai_at) - julianday(created_at))) rata
        FROM komplain WHERE status='selesai' AND selesai_at IS NOT NULL
    """
    args = []
    if bulan and tahun:
        sql += " AND strftime('%Y-%m', created_at)=?"; args.append(f"{tahun}-{bulan:02d}")
    row = db.execute(sql, args).fetchone()
    return round(row['rata'], 1) if row and row['rata'] else 0
