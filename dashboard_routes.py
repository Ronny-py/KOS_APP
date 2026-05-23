"""
routes/dashboard_routes.py
"""
from flask import Blueprint, render_template, session
from utils.auth import login_required
from utils.format_helper import bulan_sekarang, rupiah
from models.database import get_db
from datetime import date

dashboard_bp = Blueprint('dashboard', __name__)


def _info_expiry():
    """Return dict: sisa_hari, expired_at_str. Keduanya None kalau error."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT expired_at FROM admin WHERE id = ?",
            (session.get("admin_id"),)
        ).fetchone()
        if not row or not row["expired_at"]:
            return {"sisa_hari": None, "expired_at_str": None}
        exp      = date.fromisoformat(str(row["expired_at"])[:10])
        sisa     = (exp - date.today()).days
        tgl_str  = exp.strftime("%d %b %Y")   # contoh: 11 Jul 2026
        return {"sisa_hari": sisa, "expired_at_str": tgl_str}
    except Exception:
        return {"sisa_hari": None, "expired_at_str": None}


@dashboard_bp.route('/')
@login_required
def index():
    bln  = bulan_sekarang()
    conn = get_db()

    total_penghuni = conn.execute(
        "SELECT COUNT(*) as c FROM penghuni WHERE aktif=1"
    ).fetchone()['c']

    total_tagihan_bln = conn.execute(
        "SELECT COUNT(*) as c FROM tagihan WHERE bulan=?", (bln,)
    ).fetchone()['c']

    lunas_bln = conn.execute(
        "SELECT COUNT(*) as c FROM tagihan WHERE bulan=? AND status='lunas'", (bln,)
    ).fetchone()['c']

    belum_bln = conn.execute(
        "SELECT COUNT(*) as c FROM tagihan WHERE bulan=? AND status='belum'", (bln,)
    ).fetchone()['c']

    pemasukan_bln = conn.execute(
        """SELECT COALESCE(SUM(pm.jumlah_bayar),0) as total
           FROM pembayaran pm
           JOIN tagihan t ON pm.tagihan_id = t.id
           WHERE t.bulan=?""", (bln,)
    ).fetchone()['total']

    pembayaran_terbaru = conn.execute("""
        SELECT pm.*, p.nama, p.nomor_kamar, t.bulan
        FROM pembayaran pm
        JOIN penghuni p ON pm.penghuni_id = p.id
        JOIN tagihan  t ON pm.tagihan_id  = t.id
        ORDER BY pm.tanggal_bayar DESC
        LIMIT 5
    """).fetchall()

    tagihan_belum = conn.execute("""
        SELECT t.*, p.nama, p.nomor_kamar
        FROM tagihan t
        JOIN penghuni p ON t.penghuni_id = p.id
        WHERE t.status IN ('belum','sebagian')
        ORDER BY t.bulan DESC
        LIMIT 8
    """).fetchall()

    conn.close()

    expiry = _info_expiry()

    return render_template('dashboard.html',
        bln=bln,
        total_penghuni=total_penghuni,
        total_tagihan_bln=total_tagihan_bln,
        lunas_bln=lunas_bln,
        belum_bln=belum_bln,
        pemasukan_bln=rupiah(pemasukan_bln),
        pembayaran_terbaru=pembayaran_terbaru,
        tagihan_belum=tagihan_belum,
        sisa_hari=expiry["sisa_hari"],
        expired_at_str=expiry["expired_at_str"],
    )
