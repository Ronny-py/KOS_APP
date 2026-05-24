"""
PATCH untuk routes/auth_routes.py
==================================
Tambahkan 2 baris import di atas (setelah import yang sudah ada):

    from utils.activity_logger import log_login, get_client_ip

──────────────────────────────────────────────────────────
DALAM FUNGSI login() — setelah set session (LOGIN SUKSES):
──────────────────────────────────────────────────────────
Cari blok seperti ini (atau yang ekuivalen di auth_routes.py Anda):

    session["admin_id"]       = admin["id"]
    session["admin_username"] = admin["username"]
    session["admin_nama"]     = admin["nama"] or admin["username"]
    return redirect(url_for("dashboard.index"))

Tambahkan SEBELUM return redirect:

    log_login(
        admin_id   = admin["id"],
        username   = admin["username"],
        ip         = get_client_ip(),
        user_agent = request.headers.get("User-Agent", ""),
        status     = "success"
    )

──────────────────────────────────────────────────────────
DALAM FUNGSI login() — saat LOGIN GAGAL:
──────────────────────────────────────────────────────────
Cari baris flash("Username atau password salah...") atau sejenisnya,
tambahkan SEBELUM baris flash tersebut:

    log_login(
        admin_id   = None,
        username   = request.form.get("username", "").strip(),
        ip         = get_client_ip(),
        user_agent = request.headers.get("User-Agent", ""),
        status     = "failed"
    )
"""

# ── Contoh lengkap fungsi login setelah di-patch ──────────────────────────────
CONTOH_LOGIN_PATCHED = '''
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_id"):
        return redirect(url_for("dashboard.index"))

    show_kode = False
    # ... (kode existing lainnya) ...

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db  = get_db()
        admin = db.execute(
            "SELECT * FROM admin WHERE username = ?", (username,)
        ).fetchone()

        if admin and check_password(admin["password"], password):
            # ── SET SESSION ──
            session["admin_id"]       = admin["id"]
            session["admin_username"] = admin["username"]
            session["admin_nama"]     = admin["nama"] or admin["username"]

            # ── CATAT LOGIN SUKSES ─────────────────────── ← TAMBAHKAN INI
            log_login(
                admin_id   = admin["id"],
                username   = admin["username"],
                ip         = get_client_ip(),
                user_agent = request.headers.get("User-Agent", ""),
                status     = "success"
            )
            # ────────────────────────────────────────────────────────────

            return redirect(url_for("dashboard.index"))
        else:
            # ── CATAT LOGIN GAGAL ──────────────────────── ← TAMBAHKAN INI
            log_login(
                admin_id   = None,
                username   = username,
                ip         = get_client_ip(),
                user_agent = request.headers.get("User-Agent", ""),
                status     = "failed"
            )
            # ────────────────────────────────────────────────────────────
            flash("Username atau password salah.", "danger")

    return render_template("login.html", show_kode=show_kode)
'''
