"""
routes/wa_scheduler_routes.py
Halaman monitoring WA scheduler — status, preview H-3, log pengiriman.
"""

from flask import Blueprint, render_template
from utils.auth import login_required
from datetime import date, timedelta

wa_scheduler_bp = Blueprint('wa_scheduler', __name__, url_prefix='/wa-scheduler')


@wa_scheduler_bp.route('/status')
@login_required
def status():
    """
    Halaman monitoring:
    - Status scheduler (aktif/mati + next run)
    - Preview penghuni yang akan kena notif H-3 hari ini
    - Log 20 pengiriman terakhir
    """
    from utils.scheduler import _scheduler
    from models.database import get_db

    # ── Status scheduler ─────────────────────────────────────────────────────
    scheduler_running = bool(_scheduler and _scheduler.running)
    next_run = None
    if scheduler_running:
        job = _scheduler.get_job('notif_tagihan_harian')
        if job and job.next_run_time:
            next_run = job.next_run_time.strftime('%d-%m-%Y %H:%M WIB')

    # ── Preview H-3 ──────────────────────────────────────────────────────────
    target_date = (date.today() + timedelta(days=3)).isoformat()
    conn = get_db()

    preview_h3 = conn.execute("""
        SELECT
            p.nama, p.no_hp, p.nomor_kamar,
            t.bulan, t.jumlah, t.tanggal_jatuh_tempo, t.wa_count,
            COALESCE(SUM(pb.jumlah_bayar), 0) AS total_bayar
        FROM tagihan t
        JOIN penghuni p ON p.id = t.penghuni_id
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE t.tanggal_jatuh_tempo = ?
          AND t.status != 'lunas'
          AND p.aktif = 1
          AND p.no_hp IS NOT NULL AND p.no_hp != ''
        GROUP BY t.id
        ORDER BY p.nama
    """, (target_date,)).fetchall()

    # ── Log terakhir ─────────────────────────────────────────────────────────
    recent_logs = conn.execute("""
        SELECT
            nw.status, nw.error_msg, nw.tanggal_kirim,
            p.nama, p.nomor_kamar
        FROM notif_wa nw
        JOIN penghuni p ON p.id = nw.penghuni_id
        ORDER BY nw.tanggal_kirim DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    return render_template(
        'wa_scheduler/status.html',
        scheduler_running=scheduler_running,
        next_run=next_run,
        target_date=target_date,
        preview_h3=[dict(r) for r in preview_h3],
        recent_logs=[dict(r) for r in recent_logs],
    )
