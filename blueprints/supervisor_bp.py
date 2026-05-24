"""
blueprints/supervisor_bp.py
Blueprint untuk semua fungsionalitas Supervisor di KostPay.

Daftarkan ke app.py:
    from blueprints.supervisor_bp import supervisor_bp
    app.register_blueprint(supervisor_bp, url_prefix='/supervisor')

Supervisor punya dua jenis akses:
  1. Menu supervisor sendiri  → pakai @supervisor_required
  2. Semua halaman admin      → ganti @login_required → @admin_or_supervisor_required
                                di blueprint admin masing-masing
"""

from flask import (
    Blueprint, render_template, request, session,
    redirect, url_for, flash
)
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

from models.database import get_db
from utils.auth import supervisor_required

supervisor_bp = Blueprint('supervisor_bp', __name__)


# ══════════════════════════════════════════════════════════════
#  LOGIN & LOGOUT
# ══════════════════════════════════════════════════════════════

@supervisor_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'supervisor_id' in session:
        return redirect(url_for('supervisor_bp.dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()
        sv = conn.execute(
            "SELECT * FROM supervisor WHERE username = ? AND aktif = 1",
            (username,)
        ).fetchone()

        if sv and check_password_hash(sv['password'], password):
            session.clear()
            session['supervisor_id']   = sv['id']
            session['supervisor_nama'] = sv['nama']
            session['supervisor_user'] = sv['username']
            conn.execute(
                "INSERT INTO log_login_supervisor (supervisor_id, username, berhasil, ip) VALUES (?,?,1,?)",
                (sv['id'], username, request.remote_addr)
            )
            conn.commit()
            conn.close()
            flash(f'Selamat datang, {sv["nama"]}!', 'success')
            return redirect(url_for('supervisor_bp.dashboard'))
        else:
            error = 'Username atau password salah.'
            sv_id = sv['id'] if sv else None
            conn.execute(
                "INSERT INTO log_login_supervisor (supervisor_id, username, berhasil, ip) VALUES (?,?,0,?)",
                (sv_id, username, request.remote_addr)
            )
            conn.commit()
            conn.close()

    return render_template('supervisor/login.html', error=error)


@supervisor_bp.route('/logout')
def logout():
    session.clear()
    flash('Berhasil keluar dari sesi supervisor.', 'success')
    return redirect(url_for('supervisor_bp.login'))


# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════

@supervisor_bp.route('/dashboard')
@supervisor_required
def dashboard():
    conn  = get_db()
    today = date.today().isoformat()
    stats = {}

    stats['total_admin'] = conn.execute("SELECT COUNT(*) FROM admin").fetchone()[0]
    stats['login_hari_ini'] = conn.execute(
        "SELECT COUNT(*) FROM log_login_admin WHERE DATE(waktu)=? AND berhasil=1", (today,)
    ).fetchone()[0]
    stats['login_gagal'] = conn.execute(
        "SELECT COUNT(*) FROM log_login_admin WHERE DATE(waktu)=? AND berhasil=0", (today,)
    ).fetchone()[0]
    stats['aktivitas_7hari'] = conn.execute(
        "SELECT COUNT(*) FROM log_aktivitas WHERE waktu >= DATE('now','-7 days')"
    ).fetchone()[0]

    recent_aktivitas = conn.execute(
        "SELECT * FROM log_aktivitas ORDER BY waktu DESC LIMIT 10"
    ).fetchall()
    recent_login = conn.execute(
        "SELECT * FROM log_login_admin ORDER BY waktu DESC LIMIT 5"
    ).fetchall()

    conn.close()
    return render_template(
        'supervisor/dashboard.html',
        stats=stats,
        recent_aktivitas=recent_aktivitas,
        recent_login=recent_login,
    )


# ══════════════════════════════════════════════════════════════
#  LOG LOGIN ADMIN
# ══════════════════════════════════════════════════════════════

@supervisor_bp.route('/log-login')
@supervisor_required
def login_log():
    conn   = get_db()
    page   = request.args.get('page', 1, type=int)
    per    = 30
    q      = request.args.get('q', '').strip()
    status = request.args.get('status', '')
    tgl    = request.args.get('tgl', '')

    where, params = [], []
    if q:
        where.append("username LIKE ?"); params.append(f'%{q}%')
    if status == 'berhasil':
        where.append("berhasil=1")
    elif status == 'gagal':
        where.append("berhasil=0")
    if tgl:
        where.append("DATE(waktu)=?"); params.append(tgl)

    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    total  = conn.execute(f"SELECT COUNT(*) FROM log_login_admin {clause}", params).fetchone()[0]
    logs   = conn.execute(
        f"SELECT * FROM log_login_admin {clause} ORDER BY waktu DESC LIMIT ? OFFSET ?",
        [*params, per, (page - 1) * per]
    ).fetchall()
    conn.close()

    return render_template(
        'supervisor/login_log.html',
        logs=logs, page=page, per=per, total=total,
        q=q, status=status, tgl=tgl,
    )


# ══════════════════════════════════════════════════════════════
#  LOG AKTIVITAS MENU
# ══════════════════════════════════════════════════════════════

@supervisor_bp.route('/log-aktivitas')
@supervisor_required
def activity_log():
    conn  = get_db()
    page  = request.args.get('page', 1, type=int)
    per   = 30
    q     = request.args.get('q', '').strip()
    menu  = request.args.get('menu', '')
    tgl   = request.args.get('tgl', '')

    where, params = [], []
    if q:
        where.append("(admin_nama LIKE ? OR keterangan LIKE ? OR aksi LIKE ?)")
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])
    if menu:
        where.append("menu=?"); params.append(menu)
    if tgl:
        where.append("DATE(waktu)=?"); params.append(tgl)

    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    total  = conn.execute(f"SELECT COUNT(*) FROM log_aktivitas {clause}", params).fetchone()[0]
    logs   = conn.execute(
        f"SELECT * FROM log_aktivitas {clause} ORDER BY waktu DESC LIMIT ? OFFSET ?",
        [*params, per, (page - 1) * per]
    ).fetchall()
    menus  = conn.execute("SELECT DISTINCT menu FROM log_aktivitas ORDER BY menu").fetchall()
    conn.close()

    return render_template(
        'supervisor/activity_log.html',
        logs=logs, page=page, per=per, total=total,
        q=q, menu=menu, tgl=tgl, menus=menus,
    )


# ══════════════════════════════════════════════════════════════
#  GANTI PASSWORD
# ══════════════════════════════════════════════════════════════

@supervisor_bp.route('/ganti-password', methods=['GET', 'POST'])
@supervisor_required
def ganti_password():
    if request.method == 'POST':
        lama  = request.form.get('password_lama', '')
        baru  = request.form.get('password_baru', '').strip()
        ulang = request.form.get('password_ulang', '').strip()

        conn = get_db()
        sv   = conn.execute(
            "SELECT * FROM supervisor WHERE id=?", (session['supervisor_id'],)
        ).fetchone()

        if not check_password_hash(sv['password'], lama):
            flash('Password lama tidak sesuai.', 'danger')
        elif len(baru) < 8:
            flash('Password baru minimal 8 karakter.', 'danger')
        elif baru != ulang:
            flash('Konfirmasi password tidak cocok.', 'danger')
        else:
            conn.execute(
                "UPDATE supervisor SET password=? WHERE id=?",
                (generate_password_hash(baru), session['supervisor_id'])
            )
            conn.commit()
            conn.close()
            flash('Password berhasil diubah.', 'success')
            return redirect(url_for('supervisor_bp.dashboard'))

        conn.close()

    return render_template('supervisor/ganti_password.html')
