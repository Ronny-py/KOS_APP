"""
utils/scheduler.py
Scheduler harian: kirim notifikasi WA untuk tagihan yang sudah/hampir jatuh tempo.

Jadwal:
  - H-3  : reminder awal (belum lewat jatuh tempo)
  - H+0  : hari-H jatuh tempo
  - H+1+ : tagihan sudah melewati jatuh tempo

Anti-double:
  - Cek tabel notif_wa — jika hari ini sudah ada status 'sent' untuk penghuni,
    skip. Aman di-restart berkali-kali.

Catch-up startup:
  - Langsung jalan sekali saat app dinyalakan (jam berapapun),
    lalu ikut jadwal rutin jam 08:00 WIB.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Referensi global — dipakai halaman status
_scheduler = None


def _cek_dan_kirim(app):
    """
    Fungsi utama scheduler: cek tagihan & kirim WA.
    Dipanggil dalam app context.
    """
    from models.database import get_db
    from utils.wa_service import kirim_wa, buat_pesan_tagihan

    with app.app_context():
        hari_ini     = date.today()
        tiga_hari    = (hari_ini + timedelta(days=3)).isoformat()
        hari_ini_str = hari_ini.isoformat()

        conn = get_db()
        try:
            # Ambil tagihan yang:
            # 1. Belum lunas
            # 2. Jatuh tempo <= hari ini ATAU = H+3
            # 3. Penghuni aktif & punya nomor HP
            # 4. Belum ada notif 'sent' hari ini (anti-double)
            tagihan_list = conn.execute("""
                SELECT t.id AS tagihan_id, t.penghuni_id, t.bulan, t.jumlah,
                       t.tanggal_jatuh_tempo, t.status, t.wa_count,
                       p.nama, p.nomor_kamar, p.no_hp
                FROM tagihan t
                JOIN penghuni p ON t.penghuni_id = p.id
                WHERE t.status IN ('belum', 'sebagian')
                  AND p.aktif = 1
                  AND p.no_hp IS NOT NULL
                  AND p.no_hp != ''
                  AND (
                      t.tanggal_jatuh_tempo <= ?
                      OR t.tanggal_jatuh_tempo = ?
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM notif_wa nw
                      WHERE nw.penghuni_id = p.id
                        AND DATE(nw.tanggal_kirim) = DATE('now', 'localtime')
                        AND nw.status = 'sent'
                  )
            """, (hari_ini_str, tiga_hari)).fetchall()

            logger.info(f"[Scheduler] Cek tagihan: {len(tagihan_list)} tagihan perlu notif")

            for t in tagihan_list:
                total_bayar = conn.execute(
                    "SELECT COALESCE(SUM(jumlah_bayar),0) AS total FROM pembayaran WHERE tagihan_id=?",
                    (t["tagihan_id"],)
                ).fetchone()["total"]
                sisa = t["jumlah"] - total_bayar

                pesan  = buat_pesan_tagihan(dict(t), sisa=sisa)
                sukses, error = kirim_wa(t["no_hp"], pesan)

                status_log = 'sent' if sukses else 'failed'
                error_msg  = error if not sukses else None

                # Log ke notif_wa
                conn.execute("""
                    INSERT INTO notif_wa (penghuni_id, pesan, status, error_msg)
                    VALUES (?, ?, ?, ?)
                """, (t["penghuni_id"], pesan, status_log, error_msg))

                if sukses:
                    # Update flag & counter di tagihan
                    conn.execute("""
                        UPDATE tagihan
                        SET notif_wa_terkirim = 1,
                            wa_count = wa_count + 1
                        WHERE id = ?
                    """, (t["tagihan_id"],))
                    logger.info(f"[Scheduler] ✅ WA terkirim → {t['nama']} ({t['nomor_kamar']})")
                else:
                    logger.warning(f"[Scheduler] ❌ Gagal kirim ke {t['nama']}: {error}")

            conn.commit()

        except Exception as e:
            logger.error(f"[Scheduler] Error: {e}")
        finally:
            conn.close()


def start_scheduler(app):
    """
    Daftarkan dan jalankan APScheduler.
    - Langsung jalankan sekali saat startup (catch-up)
    - Lalu jalan otomatis tiap hari jam 08:00 WIB
    Panggil sekali dari create_app() di app.py.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("[Scheduler] Scheduler sudah berjalan, skip init.")
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Jakarta")

    _scheduler.add_job(
        func=_cek_dan_kirim,
        args=[app],
        trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Jakarta"),
        id="notif_tagihan_harian",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info("[Scheduler] ✅ Scheduler aktif — jalan tiap hari 08:00 WIB")

    # Catch-up: jalan 30 detik setelah startup
    # Diberi jeda agar WA server sempat load sesi sebelum kirim
    from datetime import datetime, timedelta as _td
    run_at = datetime.now() + _td(seconds=30)
    _scheduler.add_job(
        func=_cek_dan_kirim,
        args=[app],
        trigger='date',
        run_date=run_at,
        id="notif_startup_catchup",
        replace_existing=True,
    )
    logger.info(f"[Scheduler] 🚀 Catch-up startup dijadwalkan 30 detik lagi ({run_at.strftime('%H:%M:%S')})")

    return _scheduler
