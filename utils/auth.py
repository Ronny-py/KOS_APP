"""
utils/auth.py
Helper autentikasi berbasis Flask session.
Mendukung tiga level akses: admin, supervisor, dan admin_or_supervisor.
"""
from functools import wraps
from flask import session, redirect, url_for, flash


# ─────────────────────────────────────────────
#  ADMIN — akses halaman admin biasa
# ─────────────────────────────────────────────
def login_required(f):
    """Decorator: redirect ke login jika belum login sebagai admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
#  SUPERVISOR — akses halaman supervisor saja
# ─────────────────────────────────────────────
def supervisor_required(f):
    """Decorator: redirect ke login supervisor jika belum login sebagai supervisor."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'supervisor_id' not in session:
            flash('Silakan login sebagai supervisor terlebih dahulu.', 'warning')
            return redirect(url_for('supervisor_bp.login'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
#  ADMIN OR SUPERVISOR — akses gabungan
#  Ganti login_required dengan ini di route admin
#  agar supervisor bisa masuk juga
# ─────────────────────────────────────────────
def admin_or_supervisor_required(f):
    """
    Mengizinkan admin ATAU supervisor mengakses halaman.
    - Admin      : session['admin_id'] ada       → lanjut normal
    - Supervisor : session['supervisor_id'] ada  → lanjut, set _acting_as='supervisor'
    - Keduanya tidak ada → redirect ke /login
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        is_admin      = 'admin_id'      in session
        is_supervisor = 'supervisor_id' in session

        if not is_admin and not is_supervisor:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))

        # Tandai siapa yang sedang aktif (berguna di template)
        session['_acting_as'] = 'admin' if is_admin else 'supervisor'

        return f(*args, **kwargs)
    return decorated
