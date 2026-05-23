"""
models/pengeluaran_model.py
CRUD untuk tabel pengeluaran.
"""
from models.database import get_db


def get_all(bulan: int = None, tahun: int = None, kategori: str = None):
    db = get_db()
    q  = "SELECT * FROM pengeluaran WHERE 1=1"
    p  = []
    if bulan and tahun:
        q += " AND strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?"
        p += [f"{bulan:02d}", str(tahun)]
    if kategori:
        q += " AND kategori = ?"
        p.append(kategori)
    q += " ORDER BY tanggal DESC"
    rows = db.execute(q, p).fetchall()
    db.close()
    return rows


def get_by_id(eid: int):
    db  = get_db()
    row = db.execute("SELECT * FROM pengeluaran WHERE id = ?", (eid,)).fetchone()
    db.close()
    return row


def tambah(tanggal: str, kategori: str, keterangan: str, jumlah: float):
    db = get_db()
    db.execute(
        "INSERT INTO pengeluaran (tanggal, kategori, keterangan, jumlah) VALUES (?,?,?,?)",
        (tanggal, kategori, keterangan, jumlah)
    )
    db.commit()
    db.close()


def update(eid: int, tanggal: str, kategori: str, keterangan: str, jumlah: float):
    db = get_db()
    db.execute(
        "UPDATE pengeluaran SET tanggal=?, kategori=?, keterangan=?, jumlah=? WHERE id=?",
        (tanggal, kategori, keterangan, jumlah, eid)
    )
    db.commit()
    db.close()


def hapus(eid: int):
    db = get_db()
    db.execute("DELETE FROM pengeluaran WHERE id = ?", (eid,))
    db.commit()
    db.close()


def get_kategori_list():
    db   = get_db()
    rows = db.execute(
        "SELECT DISTINCT kategori FROM pengeluaran WHERE kategori IS NOT NULL ORDER BY kategori"
    ).fetchall()
    db.close()
    return [r['kategori'] for r in rows]


def get_summary_kategori(bulan: int, tahun: int):
    db   = get_db()
    rows = db.execute("""
        SELECT kategori, SUM(jumlah) AS total
        FROM pengeluaran
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
        GROUP BY kategori
        ORDER BY total DESC
    """, (f"{bulan:02d}", str(tahun))).fetchall()
    db.close()
    return rows


def get_tahun_list():
    db   = get_db()
    rows = db.execute(
        "SELECT DISTINCT strftime('%Y', tanggal) AS tahun FROM pengeluaran ORDER BY tahun DESC"
    ).fetchall()
    db.close()
    import datetime
    return [int(r['tahun']) for r in rows] or [datetime.date.today().year]
