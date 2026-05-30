"""
routes/wa_scheduler_routes.py
Halaman monitoring WA scheduler — status, preview H & H+3, log pengiriman.
"""
from flask import Blueprint, render_template
from utils.auth import login_required
from datetime import date, timedelta

wa_scheduler_bp = Blueprint('wa_scheduler', __name__, url_prefix='/wa-scheduler')


@wa_scheduler_bp.route('/status')
@login_required
def status():
    from utils.scheduler import _scheduler
    from models.database import get_db

    # ── Status scheduler ─────────────────────────────────────────────────────
    scheduler_running = bool(_scheduler and _scheduler.running)
    next_run = None
    if scheduler_running:
        job = _scheduler.get_job('notif_tagihan_harian')
        if job and job.next_run_time:
            next_run = job.next_run_time.strftime('%d-%m-%Y %H:%M WIB')

    today      = date.today()
    tanggal_H  = today.isoformat()
    tanggal_H3 = (today - timedelta(days=3)).isoformat()

    conn = get_db()

    def fetch_preview(tgl_jt, tipe):
        return conn.execute("""
            SELECT
                p.nama, p.no_hp, p.nomor_kamar,
                t.id AS tagihan_id,
                t.bulan, t.jumlah, t.tanggal_jatuh_tempo, t.wa_count,
                COALESCE(SUM(pb.jumlah_bayar), 0) AS total_bayar,
                EXISTS (
                    SELECT 1 FROM notif_wa nw
                    WHERE nw.tipe_notif = ?
                      AND nw.status     = 'sent'
                      AND (
                          nw.tagihan_id = t.id
                          OR (
                              nw.tagihan_id IS NULL
                              AND nw.penghuni_id = p.id
                              AND nw.pesan LIKE '%' || t.bulan || '%'
                          )
                      )
                ) AS sudah_terkirim
            FROM tagihan t
            JOIN penghuni p ON p.id = t.penghuni_id
            LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
            WHERE t.tanggal_jatuh_tempo = ?
              AND t.status IN ('belum', 'sebagian')
              AND p.aktif = 1
              AND p.no_hp IS NOT NULL AND p.no_hp != ''
            GROUP BY t.id
            ORDER BY p.nama
        """, (tipe, tgl_jt)).fetchall()

    preview_H  = fetch_preview(tanggal_H,  'H')
    preview_H3 = fetch_preview(tanggal_H3, 'H+3')

    # ── Log 20 terakhir ───────────────────────────────────────────────────────
    recent_logs = conn.execute("""
        SELECT
            nw.status, nw.error_msg, nw.tanggal_kirim,
            nw.tipe_notif,
            p.nama, p.nomor_kamar
        FROM notif_wa nw
        JOIN penghuni p ON p.id = nw.penghuni_id
        ORDER BY nw.tanggal_kirim DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    return render_template(
        'wa_scheduler/status.html',
        scheduler_running = scheduler_running,
        next_run          = next_run,
        tanggal_H         = tanggal_H,
        tanggal_H3        = tanggal_H3,
        preview_H         = [dict(r) for r in preview_H],
        preview_H3        = [dict(r) for r in preview_H3],
        recent_logs       = [dict(r) for r in recent_logs],
    )
