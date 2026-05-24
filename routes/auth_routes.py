"""
routes/auth_routes.py
Login / Logout — dengan validasi expiry anti-manipulasi waktu.

Kode khusus di-generate otomatis dari tanggal login terakhir (last_seen
atau max_date_seen). Format: YYMMDD
  Contoh: last_seen = "2026-08-07 09:47:20"  →  kode = "260807"

Tidak ada kode statis — kode selalu berbeda tiap user/waktu.
"""
from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)
from werkzeug.security import check_password_hash
from models.database import get_db
from utils.license_guard import validasi_expiry, update_timestamps
from utils.activity_logger import log_login, get_client_ip

auth_bp = Blueprint("auth", __name__)


def _generate_kode(last_seen: str) -> str:
    """
    Generate kode khusus dari string tanggal login terakhir.
    Format input  : "YYYY-MM-DD HH:MM:SS"  atau  "YYYY-MM-DD"
    Format output : "YYMMDD"
    Contoh        : "2026-08-07 09:47:20"  →  "260807"
    """
    if not last_seen:
        return ""
    # Ambil hanya bagian tanggal (sebelum spasi)
    tanggal = last_seen.strip().split(" ")[0]   # "2026-08-07"
    bagian  = tanggal.split("-")                # ["2026", "08", "07"]
    if len(bagian) < 3:
        return ""
    yy = bagian[0][-2:]   # "26"
    mm = bagian[1]        # "08"
    dd = bagian[2]        # "07"
    return f"MINIGO{yy}{mm}{dd}"                 # "MINIGO260807"


def _get_admin(username: str) -> dict | None:
    """Ambil data admin sebagai dict, atau None kalau tidak ada."""
    db  = get_db()
    cur = db.execute(
        """SELECT id, username, password, nama,
                  expired_at, last_seen, max_date_seen, expiry_token
           FROM admin WHERE username = ?""",
        (username,)
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = ["id", "username", "password", "nama",
            "expired_at", "last_seen", "max_date_seen", "expiry_token"]
    return dict(zip(keys, row))


def _do_login(admin: dict):
    """Simpan session setelah login berhasil."""
    db = get_db()
    update_timestamps(db, admin["id"])
    session.clear()
    session["admin_id"]   = admin["id"]
    session["admin_nama"] = admin["nama"] or admin["username"]
    session.permanent     = False


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", show_kode=False)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    screen   = request.form.get("_screen", "login")  # 'login' atau 'kode'

    # ── 1. Verifikasi username + password dulu ────────────────────────────────
    admin = _get_admin(username)
    if admin is None or not check_password_hash(admin["password"], password):
        log_login(
            admin_id   = admin["id"] if admin else None,
            username   = username,
            ip         = get_client_ip(),
            user_agent = request.headers.get("User-Agent", ""),
            status     = "failed"
        )
        flash("Username atau password salah.", "danger")
        return render_template("login.html",
                               show_kode=False,
                               username=username), 401

    # ── 2. Validasi expiry + anti-rollback ────────────────────────────────────
    ok, pesan = validasi_expiry(admin)

    if ok:
        # ── Login normal berhasil ─────────────────────────────────────────────
        log_login(
            admin_id   = admin["id"],
            username   = admin["username"],
            ip         = get_client_ip(),
            user_agent = request.headers.get("User-Agent", ""),
            status     = "success"
        )
        _do_login(admin)
        return redirect(url_for("dashboard.index"))

    # ── 3. Gagal validasi — tentukan jenis kegagalan ──────────────────────────
    #
    # validasi_expiry diharapkan mengembalikan pesan yang mengandung kata
    # "mundur" / "rollback" / "manipulasi" untuk kasus backdate,
    # atau "habis" / "kadaluarsa" untuk kasus expired.
    # Sesuaikan keyword di bawah dengan pesan aktual dari license_guard.py Anda.

    pesan_lower    = pesan.lower()
    is_backdate    = any(k in pesan_lower for k in ("mundur", "rollback",
                                                     "manipulasi", "tidak valid",
                                                     "backdate"))
    is_expired     = any(k in pesan_lower for k in ("habis", "kadaluarsa",
                                                     "expired", "berakhir"))
    needs_kode     = is_backdate or is_expired

    # Ambil tanggal login terakhir — prioritas max_date_seen (lebih akurat
    # untuk deteksi rollback), fallback ke last_seen
    raw_last_seen  = admin.get("max_date_seen") or admin.get("last_seen") or ""
    backdate_info  = raw_last_seen   # ditampilkan di banner template

    # Generate kode dinamis dari tanggal login terakhir
    kode_benar = _generate_kode(raw_last_seen)

    # ── 4. Jika screen == 'kode', user sudah mengisi kode khusus ─────────────
    if screen == "kode" and needs_kode:
        kode_input = request.form.get("kode_khusus", "").strip()

        if kode_input == kode_benar and kode_benar != "":
            # Kode benar — reset max_date_seen lalu login
            db = get_db()
            db.execute(
                "UPDATE admin SET max_date_seen = NULL WHERE id = ?",
                (admin["id"],)
            )
            db.commit()
            log_login(
                admin_id   = admin["id"],
                username   = admin["username"],
                ip         = get_client_ip(),
                user_agent = request.headers.get("User-Agent", ""),
                status     = "success"
            )
            _do_login(admin)
            flash("Verifikasi berhasil. Selamat datang!", "success")
            return redirect(url_for("dashboard.index"))
        else:
            flash("Kode khusus salah. Coba lagi.", "danger")
            return render_template(
                "login.html",
                show_kode=True,
                backdate_forced=is_backdate,
                backdate_info=backdate_info if is_backdate else None,
                username=username,
            ), 401

    # ── 5. Pertama kali gagal validasi — langsung tampilkan screen kode ───────
    if needs_kode:
        return render_template(
            "login.html",
            show_kode=True,
            backdate_forced=is_backdate,          # sembunyikan tombol "Kembali"
            backdate_info=backdate_info if is_backdate else None,
            username=username,
        ), 403

    # ── 6. Error lain yang tidak butuh kode (mis. token rusak) ───────────────
    flash(pesan, "danger")
    return render_template("login.html",
                           show_kode=False,
                           username=username), 403


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Anda telah logout.", "info")
    return redirect(url_for("auth.login"))
