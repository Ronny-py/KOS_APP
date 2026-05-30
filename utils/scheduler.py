"""
utils/scheduler.py
Scheduler harian: kirim notifikasi WA untuk tagihan.

Jadwal pengiriman (2 tipe, masing-masing SEKALI per tagihan):
  - Hari H  : tanggal jatuh tempo = hari ini       (tipe_notif = 'H')
  - H+3     : 3 hari setelah jatuh tempo            (tipe_notif = 'H+3')

Anti-double:
  - Sebelum kirim, cek tabel notif_wa:
    tagihan_id + tipe_notif + status='sent' → skip jika sudah ada.
  - Aman di-restart / di-run berkali-kali.

Catch-up startup:
  - Langsung jalan sekali 30 detik setelah app dinyalakan,
    lalu ikut jadwal rutin jam 08:00 WIB.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_scheduler = None


def _cek_dan_kirim(app):
    from models.database import get_db
    from utils.wa_service import kirim_wa, buat_pesan_tagihan

    with app.app_context():
        hari_ini   = date.today()
        tanggal_H  = hari_ini.isoformat()
        tanggal_H3 = (hari_ini - timedelta(days=3)).isoformat()

        conn = get_db()
        try:

            def fetch_tagihan(tgl_jt):
                return conn.execute("""
                    SELECT
                        t.id AS tagihan_id, t.penghuni_id,
                        t.bulan, t.jumlah, t.tanggal_jatuh_tempo,
                        t.status, t.wa_count,
                        p.nama, p.nomor_kamar, p.no_hp
                    FROM tagihan t
                    JOIN penghuni p ON t.penghuni_id = p.id
                    WHERE t.status IN ('belum', 'sebagian')
                      AND p.aktif = 1
                      AND p.no_hp IS NOT NULL AND p.no_hp != ''
                      AND t.tanggal_jatuh_tempo = ?
                """, (tgl_jt,)).fetchall()

            def sudah_terkirim(tagihan_id, tipe):
                """True jika tipe ini sudah pernah sukses dikirim untuk tagihan ini.
                Cek dua cara:
                  1. via tagihan_id langsung (record baru dari scheduler)
                  2. fallback via penghuni_id + bulan (record lama tagihan_id=NULL dari broadcast/manual)
                """
                # Cara 1: tagihan_id tersimpan (record baru)
                if conn.execute("""
                    SELECT 1 FROM notif_wa
                    WHERE tagihan_id = ? AND tipe_notif = ? AND status = 'sent'
                    LIMIT 1
                """, (tagihan_id, tipe)).fetchone():
                    return True

                # Cara 2: fallback untuk record lama yang tagihan_id-nya NULL
                row = conn.execute(
                    "SELECT penghuni_id, bulan FROM tagihan WHERE id = ?", (tagihan_id,)
                ).fetchone()
                if not row:
                    return False
                return conn.execute("""
                    SELECT 1 FROM notif_wa
                    WHERE tagihan_id IS NULL
                      AND penghuni_id = ?
                      AND tipe_notif  = ?
                      AND status      = 'sent'
                      AND pesan LIKE  ?
                    LIMIT 1
                """, (row["penghuni_id"], tipe, f'%{row["bulan"]}%')).fetchone() is not None

            def proses_batch(tagihan_list, tipe):
                sent = skip = fail = 0
                for t in tagihan_list:
                    tagihan_id = t["tagihan_id"]

                    if sudah_terkirim(tagihan_id, tipe):
                        skip += 1
                        logger.debug(f"[{tipe}] Skip tagihan_id={tagihan_id} ({t['nama']}) — sudah terkirim")
                        continue

                    total_bayar = conn.execute(
                        "SELECT COALESCE(SUM(jumlah_bayar),0) AS total FROM pembayaran WHERE tagihan_id=?",
                        (tagihan_id,)
                    ).fetchone()["total"]
                    sisa = t["jumlah"] - total_bayar

                    pesan = buat_pesan_tagihan(dict(t), sisa=sisa, tipe=tipe)
                    sukses, error = kirim_wa(t["no_hp"], pesan)

                    # Tulis ke notif_wa — sesuai kolom DB asli + kolom baru
                    conn.execute("""
                        INSERT INTO notif_wa
                            (penghuni_id, tagihan_id, tipe_notif, pesan, status, error_msg,
                             tanggal_kirim, tanggal_update)
                        VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
                    """, (
                        t["penghuni_id"],
                        tagihan_id,
                        tipe,
                        pesan,
                        'sent' if sukses else 'failed',
                        error if not sukses else None,
                    ))

                    if sukses:
                        conn.execute("""
                            UPDATE tagihan
                            SET notif_wa_terkirim = 1, wa_count = wa_count + 1
                            WHERE id = ?
                        """, (tagihan_id,))
                        sent += 1
                        logger.info(f"[{tipe}] ✅ Terkirim → {t['nama']} ({t['nomor_kamar']})")
                    else:
                        fail += 1
                        logger.warning(f"[{tipe}] ❌ Gagal → {t['nama']}: {error}")

                conn.commit()
                logger.info(f"[{tipe}] Selesai — sent={sent} skip={skip} fail={fail}")

            # ── Jalankan dua batch ───────────────────────────────────────────
            logger.info(f"[Scheduler] Mulai — H={tanggal_H} | H+3={tanggal_H3}")

            batch_H  = fetch_tagihan(tanggal_H)
            batch_H3 = fetch_tagihan(tanggal_H3)
            logger.info(f"[Scheduler] Ditemukan: H={len(batch_H)} tagihan | H+3={len(batch_H3)} tagihan")

            proses_batch(batch_H,  tipe="H")
            proses_batch(batch_H3, tipe="H+3")

            logger.info("[Scheduler] Semua batch selesai.")

        except Exception as e:
            logger.error(f"[Scheduler] Error: {e}", exc_info=True)
        finally:
            conn.close()


def start_scheduler(app):
    """
    Daftarkan dan jalankan APScheduler.
    Panggil sekali dari create_app() di app.py.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("[Scheduler] Sudah berjalan, skip init.")
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
    logger.info("[Scheduler] ✅ Aktif — jalan tiap hari 08:00 WIB")

    # Catch-up: jalan 30 detik setelah startup
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
    logger.info(f"[Scheduler] 🚀 Catch-up dijadwalkan pukul {run_at.strftime('%H:%M:%S')}")

    return _scheduler
