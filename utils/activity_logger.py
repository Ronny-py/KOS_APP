"""
utils/activity_logger.py
Catat setiap request dari admin ke tabel activity_log.
Dipanggil via Flask before_request hook di app.py.
"""
import requests as _req
from flask import request, session
from models.database import get_db

# Peta endpoint → label menu yang ditampilkan di dashboard supervisor
MENU_LABELS = {
    "dashboard.index":           "Dashboard",
    "penghuni.index":            "Penghuni – Daftar",
    "penghuni.tambah":           "Penghuni – Tambah",
    "penghuni.edit":             "Penghuni – Edit",
    "penghuni.hapus":            "Penghuni – Hapus",
    "tagihan.index":             "Tagihan – Daftar",
    "tagihan.tambah":            "Tagihan – Tambah",
    "tagihan.edit":              "Tagihan – Edit",
    "tagihan.hapus":             "Tagihan – Hapus",
    "pembayaran.index":          "Pembayaran – Daftar",
    "pembayaran.tambah":         "Pembayaran – Tambah",
    "pembayaran.hapus":          "Pembayaran – Hapus",
    "pengeluaran.index":         "Pengeluaran – Daftar",
    "pengeluaran.tambah":        "Pengeluaran – Tambah",
    "pengeluaran.edit":          "Pengeluaran – Edit",
    "pengeluaran.hapus":         "Pengeluaran – Hapus",
    "inventaris.index":          "Inventaris – Daftar",
    "inventaris.tambah":         "Inventaris – Tambah",
    "inventaris.edit":           "Inventaris – Edit",
    "inventaris.hapus":          "Inventaris – Hapus",
    "laporan.pembayaran":        "Laporan Pembayaran",
    "laporan.pengeluaran":       "Laporan Pengeluaran",
    "laporan_inventaris.index":  "Laporan Inventaris",
    "komplain.index":            "Komplain – Daftar",
    "komplain.detail":           "Komplain – Detail",
    "komplain.laporan":          "Laporan Komplain",
    "wa_scheduler.status":       "Status WA",
    "notif_wa.index":            "Notifikasi WA",
    "kirim_wa.kirim":            "Kirim WA",
}

# Endpoint yang diabaikan (statis, API polling, dsb.)
SKIP_ENDPOINTS = {
    "static",
    "auth.login", "auth.logout",
    "supervisor_bp.login", "supervisor_bp.logout",
    "wa_scheduler.status_json",
    "chatbot.reply",
    "bukti_transfer.upload",
    "komplain_publik.form",
    "komplain_publik.submit",
}


def get_client_ip():
    """Ambil IP asli di belakang proxy."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _geo_lookup(ip: str) -> dict:
    """Lookup lokasi via ip-api.com (gratis, tanpa key, max 45 req/menit)."""
    if ip in ("127.0.0.1", "::1", "unknown"):
        return {"city": "Localhost", "region": "-", "country": "-",
                "lat": "-", "lon": "-"}
    try:
        r = _req.get(
            f"http://ip-api.com/json/{ip}?fields=city,regionName,country,lat,lon,status",
            timeout=2
        )
        d = r.json()
        if d.get("status") == "success":
            return {
                "city":    d.get("city", "-"),
                "region":  d.get("regionName", "-"),
                "country": d.get("country", "-"),
                "lat":     str(d.get("lat", "-")),
                "lon":     str(d.get("lon", "-")),
            }
    except Exception:
        pass
    return {"city": "-", "region": "-", "country": "-", "lat": "-", "lon": "-"}


def log_login(admin_id, username, ip, user_agent, status="success"):
    """Catat event login/logout ke tabel login_log (dengan geo lookup)."""
    geo = _geo_lookup(ip)
    db = get_db()
    db.execute(
        """INSERT INTO login_log
               (admin_id, username, ip_address, user_agent,
                city, region, country, latitude, longitude, status)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (admin_id, username, ip, user_agent,
         geo["city"], geo["region"], geo["country"],
         geo["lat"], geo["lon"], status)
    )
    db.commit()


def log_activity(app):
    """
    Daftarkan before_request hook ke Flask app.
    Catat setiap akses halaman oleh admin yang sedang login.
    """
    @app.before_request
    def _track():
        # Hanya catat jika admin login (bukan supervisor)
        admin_id = session.get("admin_id")
        username = session.get("admin_username")
        if not admin_id or not username:
            return

        endpoint = request.endpoint or ""
        if not endpoint or endpoint in SKIP_ENDPOINTS:
            return
        # Abaikan request statis dan sub-resource
        if endpoint.startswith("static"):
            return

        menu_label = MENU_LABELS.get(endpoint, endpoint)
        ip = get_client_ip()

        try:
            db = get_db()
            db.execute(
                """INSERT INTO activity_log
                       (admin_id, username, endpoint, menu_label, method, ip_address)
                   VALUES (?,?,?,?,?,?)""",
                (admin_id, username, endpoint, menu_label,
                 request.method, ip)
            )
            db.commit()
        except Exception:
            pass  # Jangan sampai log error menghentikan request utama
