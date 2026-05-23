"""
utils/wa_scheduler.py
Scheduler otomatis kirim WA pengingat tagihan H-3 sebelum jatuh tempo.

Cara pakai:
    1. pip install apscheduler
    2. Panggil init_scheduler(app) di app.py / __init__.py setelah app dibuat

Logika:
    - Saat app pertama nyala → langsung cek & kirim (catch-up, jam berapapun)
    - Setiap hari jam 08:00 WIB → cek & kirim otomatis
    - Flag anti-double: cek tabel notif_wa, jika hari ini sudah ada status 'sent'
      untuk penghuni tersebut → skip, tidak kirim lagi
    - Abaikan tagihan yang sudah lunas
    - Update notif_wa_terkirim & wa_count di tabel tagihan setelah berhasil kirim
"""

import logging
from datetime import date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# ─── Query penghuni yang perlu diingatkan ────────────────────────────────────

def _get_tagihan_h3() -> list[dict]:
    """
    Ambil tagihan yang:
    - Jatuh tempo persis 3 hari dari sekarang
    - Status bukan 'lunas'
    - Penghuni aktif & punya no HP
    - Belum ada notif_wa hari ini untuk tagihan ini
    """
    from models.database import get_db

    target_date = (date.today() + timedelta(days=3)).isoformat()  # YYYY-MM-DD

    conn = get_db()
    rows = conn.execute("""
        SELECT
            p.id            AS penghuni_id,
            p.nama,
            p.no_hp,
            p.nomor_kamar,
            t.id            AS tagihan_id,
            t.bulan,
            t.jumlah,
            t.tanggal_jatuh_tempo,
            t.wa_count,
            COALESCE(SUM(pb.jumlah_bayar), 0) AS total_bayar
        FROM tagihan t
        JOIN penghuni p ON p.id = t.penghuni_id
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE
            t.tanggal_jatuh_tempo = ?       -- tepat H-3
            AND t.status != 'lunas'          -- belum lunas
            AND p.aktif = 1                  -- penghuni aktif
            AND p.no_hp IS NOT NULL
            AND p.no_hp != ''
            -- belum ada notif hari ini
            AND NOT EXISTS (
                SELECT 1 FROM notif_wa nw
                WHERE nw.penghuni_id = p.id
                  AND DATE(nw.tanggal_kirim) = DATE('now', 'localtime')
                  AND nw.status = 'sent'
            )
        GROUP BY t.id
    """, (target_date,)).fetchall()
    conn.close()

    return [dict(r) for r in rows]


# ─── Job utama ───────────────────────────────────────────────────────────────

def job_kirim_wa_h3():
    """
    Job utama: kirim WA ke penghuni yang jatuh tempo H-3.
    Dijalankan otomatis jam 08:00 WIB dan sekali saat app startup.
    Anti-double: penghuni yang sudah dapat notif 'sent' hari ini di-skip.
    """
    from models.database import get_db
    from utils.wa_service import kirim_wa, buat_pesan_tagihan

    logger.info("[WA Scheduler] Mulai cek tagihan H-3...")

    tagihan_list = _get_tagihan_h3()

    if not tagihan_list:
        logger.info("[WA Scheduler] Tidak ada tagihan H-3 hari ini.")
        return

    logger.info(f"[WA Scheduler] Ditemukan {len(tagihan_list)} tagihan akan dikirim notif.")

    conn = get_db()
    berhasil = gagal = 0

    for t in tagihan_list:
        sisa = t['jumlah'] - t['total_bayar']

        # Buat pesan
        pesan = buat_pesan_tagihan(t, sisa=sisa)

        # Kirim WA
        sukses, err = kirim_wa(t['no_hp'], pesan)

        status_log = 'sent' if sukses else 'failed'
        error_msg  = err if not sukses else None

        # Log ke notif_wa
        conn.execute("""
            INSERT INTO notif_wa (penghuni_id, pesan, status, error_msg)
            VALUES (?, ?, ?, ?)
        """, (t['penghuni_id'], pesan, status_log, error_msg))

        # Update tagihan: tandai sudah terkirim & increment wa_count
        if sukses:
            conn.execute("""
                UPDATE tagihan
                SET notif_wa_terkirim = 1,
                    wa_count = wa_count + 1
                WHERE id = ?
            """, (t['tagihan_id'],))
            berhasil += 1
            logger.info(f"[WA Scheduler] ✅ Terkirim → {t['nama']} ({t['no_hp']})")
        else:
            gagal += 1
            logger.warning(f"[WA Scheduler] ❌ Gagal → {t['nama']} | Error: {err}")

    conn.commit()
    conn.close()

    logger.info(f"[WA Scheduler] Selesai. Berhasil: {berhasil}, Gagal: {gagal}")


# ─── Init scheduler ──────────────────────────────────────────────────────────

_scheduler: BackgroundScheduler | None = None


def init_scheduler(app=None):
    """
    Inisialisasi scheduler dan langsung jalankan job sekali saat startup.

    Alur:
        1. app nyala → job langsung jalan (catch-up, jam berapapun)
        2. Selanjutnya jalan otomatis tiap hari jam 08:00 WIB
        3. Anti-double dijaga oleh query (cek notif_wa hari ini)

    Dipanggil sekali di app.py:
        from utils.wa_scheduler import init_scheduler
        init_scheduler(app)
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("[WA Scheduler] Scheduler sudah berjalan, skip init.")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Jakarta")

    if app:
        def _job_with_context():
            with app.app_context():
                job_kirim_wa_h3()

        _scheduler.add_job(
            func=_job_with_context,
            trigger=CronTrigger(hour=8, minute=0),
            id='wa_h3_reminder',
            name='WA Reminder H-3 Jatuh Tempo',
            replace_existing=True,
            misfire_grace_time=3600,
        )

        _scheduler.start()
        logger.info("[WA Scheduler] ✅ Scheduler aktif — job jalan tiap hari jam 08:00 WIB")

        # ── Catch-up: langsung kirim saat startup ────────────────────────
        # Anti-double sudah dijaga query (NOT EXISTS notif hari ini)
        logger.info("[WA Scheduler] 🚀 Catch-up startup: cek tagihan H-3 sekarang...")
        _job_with_context()

    else:
        _scheduler.add_job(
            func=job_kirim_wa_h3,
            trigger=CronTrigger(hour=8, minute=0),
            id='wa_h3_reminder',
            name='WA Reminder H-3 Jatuh Tempo',
            replace_existing=True,
            misfire_grace_time=3600,
        )

        _scheduler.start()
        logger.info("[WA Scheduler] ✅ Scheduler aktif — job jalan tiap hari jam 08:00 WIB")

        logger.info("[WA Scheduler] 🚀 Catch-up startup: cek tagihan H-3 sekarang...")
        job_kirim_wa_h3()


def stop_scheduler():
    """Hentikan scheduler (untuk graceful shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[WA Scheduler] Scheduler dihentikan.")
