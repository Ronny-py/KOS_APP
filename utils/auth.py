"""
utils/auth.py
Helper autentikasi berbasis Flask session.
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Decorator: redirect ke login jika belum login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated
