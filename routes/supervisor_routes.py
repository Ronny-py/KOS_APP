"""
routes/supervisor_routes.py
Blueprint untuk akun Supervisor:
 - Login / Logout supervisor (session terpisah dari admin)
 - Dashboard log login admin
 - Dashboard log akses menu admin
"""
import hashlib
from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash
)
from models.database import get_db
from utils.activity_logger import log_login, get_client_ip

supervisor_bp = Blueprint("supervisor_bp", __name__, url_prefix="/supervisor")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _sv_required(f):
    """Decorator: pastikan supervisor sudah login."""
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("supervisor_id"):
            return redirect(url_for("supervisor_bp.login"))
        return f(*args, **kwargs)
    return wrapped


# ── Login / Logout ────────────────────────────────────────────────────────────

@supervisor_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("supervisor_id"):
        return redirect(url_for("supervisor_bp.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        sv = db.execute(
            "SELECT * FROM supervisor WHERE username = ? AND aktif = 1",
            (username,)
        ).fetchone()

        if sv and sv["password"] == _hash(password):
            session["supervisor_id"]       = sv["id"]
            session["supervisor_username"] = sv["username"]
            session["supervisor_nama"]     = sv["nama"] or sv["username"]
            return redirect(url_for("supervisor_bp.dashboard"))
        else:
            flash("Username atau password supervisor salah.", "danger")

    return render_template("supervisor/login.html")


@supervisor_bp.route("/logout")
def logout():
    session.pop("supervisor_id", None)
    session.pop("supervisor_username", None)
    session.pop("supervisor_nama", None)
    return redirect(url_for("supervisor_bp.login"))


# ── Dashboard utama ───────────────────────────────────────────────────────────

@supervisor_bp.route("/")
@supervisor_bp.route("/dashboard")
@_sv_required
def dashboard():
    db = get_db()

    # Statistik ringkas
    total_login   = db.execute("SELECT COUNT(*) FROM login_log").fetchone()[0]
    login_sukses  = db.execute("SELECT COUNT(*) FROM login_log WHERE status='success'").fetchone()[0]
    login_gagal   = db.execute("SELECT COUNT(*) FROM login_log WHERE status='failed'").fetchone()[0]
    total_aksi    = db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]

    # 10 login terakhir
    recent_logins = db.execute("""
        SELECT * FROM login_log
        ORDER BY created_at DESC LIMIT 10
    """).fetchall()

    # 10 aktivitas terakhir
    recent_activity = db.execute("""
        SELECT * FROM activity_log
        ORDER BY created_at DESC LIMIT 10
    """).fetchall()

    # Top menu yang paling sering diakses
    top_menu = db.execute("""
        SELECT menu_label, COUNT(*) as cnt
        FROM activity_log
        GROUP BY menu_label
        ORDER BY cnt DESC LIMIT 8
    """).fetchall()

    return render_template(
        "supervisor/dashboard.html",
        total_login=total_login,
        login_sukses=login_sukses,
        login_gagal=login_gagal,
        total_aksi=total_aksi,
        recent_logins=recent_logins,
        recent_activity=recent_activity,
        top_menu=top_menu,
    )


# ── Log Login (semua data) ────────────────────────────────────────────────────

@supervisor_bp.route("/login-log")
@_sv_required
def login_log():
    db  = get_db()
    username_filter = request.args.get("username", "").strip()
    status_filter   = request.args.get("status", "").strip()
    page  = max(int(request.args.get("page", 1)), 1)
    limit = 30
    offset = (page - 1) * limit

    where_clauses = []
    params = []
    if username_filter:
        where_clauses.append("username LIKE ?")
        params.append(f"%{username_filter}%")
    if status_filter:
        where_clauses.append("status = ?")
        params.append(status_filter)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM login_log {where_sql}", params
    ).fetchone()[0]

    logs = db.execute(
        f"""SELECT * FROM login_log {where_sql}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()

    # Hitung total login per user
    per_user = db.execute("""
        SELECT username, COUNT(*) as total,
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as sukses,
               SUM(CASE WHEN status='failed'  THEN 1 ELSE 0 END) as gagal,
               MAX(created_at) as terakhir
        FROM login_log
        GROUP BY username
        ORDER BY total DESC
    """).fetchall()

    total_pages = (total + limit - 1) // limit

    return render_template(
        "supervisor/login_log.html",
        logs=logs,
        per_user=per_user,
        total=total,
        page=page,
        total_pages=total_pages,
        username_filter=username_filter,
        status_filter=status_filter,
    )


# ── Log Aktivitas Menu ────────────────────────────────────────────────────────

@supervisor_bp.route("/activity-log")
@_sv_required
def activity_log():
    db  = get_db()
    username_filter = request.args.get("username", "").strip()
    menu_filter     = request.args.get("menu", "").strip()
    page  = max(int(request.args.get("page", 1)), 1)
    limit = 30
    offset = (page - 1) * limit

    where_clauses = []
    params = []
    if username_filter:
        where_clauses.append("username LIKE ?")
        params.append(f"%{username_filter}%")
    if menu_filter:
        where_clauses.append("menu_label LIKE ?")
        params.append(f"%{menu_filter}%")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM activity_log {where_sql}", params
    ).fetchone()[0]

    logs = db.execute(
        f"""SELECT * FROM activity_log {where_sql}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()

    # Rekapitulasi per menu
    menu_recap = db.execute("""
        SELECT menu_label, COUNT(*) as cnt
        FROM activity_log
        GROUP BY menu_label
        ORDER BY cnt DESC
    """).fetchall()

    total_pages = (total + limit - 1) // limit

    return render_template(
        "supervisor/activity_log.html",
        logs=logs,
        menu_recap=menu_recap,
        total=total,
        page=page,
        total_pages=total_pages,
        username_filter=username_filter,
        menu_filter=menu_filter,
    )


# ── Ganti Password Supervisor ─────────────────────────────────────────────────

@supervisor_bp.route("/ganti-password", methods=["GET", "POST"])
@_sv_required
def ganti_password():
    if request.method == "POST":
        lama  = request.form.get("password_lama", "")
        baru  = request.form.get("password_baru", "")
        ulang = request.form.get("password_ulang", "")

        db = get_db()
        sv = db.execute(
            "SELECT * FROM supervisor WHERE id = ?",
            (session["supervisor_id"],)
        ).fetchone()

        if sv["password"] != _hash(lama):
            flash("Password lama salah.", "danger")
        elif len(baru) < 6:
            flash("Password baru minimal 6 karakter.", "danger")
        elif baru != ulang:
            flash("Konfirmasi password tidak cocok.", "danger")
        else:
            db.execute(
                "UPDATE supervisor SET password = ? WHERE id = ?",
                (_hash(baru), session["supervisor_id"])
            )
            db.commit()
            flash("Password berhasil diubah.", "success")
            return redirect(url_for("supervisor_bp.dashboard"))

    return render_template("supervisor/ganti_password.html")
