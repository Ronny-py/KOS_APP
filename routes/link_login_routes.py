"""
routes/link_login_routes.py
Melayani halaman publik yang bisa diakses dari halaman login
(kamar_kosong, harga_sewa, fasilitas, cara_bayar)
"""
from flask import Blueprint, render_template, abort

link_login_bp = Blueprint('link_login', __name__)

HALAMAN_IZIN = {'kamar_kosong', 'harga_sewa', 'fasilitas', 'cara_bayar', 'cek_komplain'}

@link_login_bp.route('/link_login/<halaman>')
def tampil(halaman):
    if halaman not in HALAMAN_IZIN:
        abort(404)
    return render_template(f'link_login/{halaman}.html')
