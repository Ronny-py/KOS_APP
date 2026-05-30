"""
routes/qr_routes.py
Portal QR Code per kamar — akses via PIN tanpa login admin.

Endpoints:
  GET  /qr/admin              → halaman admin generate & print semua QR
  GET  /qr/<nomor_kamar>      → landing page PIN (publik)
  POST /qr/<nomor_kamar>/auth → verifikasi PIN → set session
  GET  /qr/<nomor_kamar>/portal → halaman portal (butuh PIN session)
  POST /qr/<nomor_kamar>/komplain → submit komplain
  POST /qr/<nomor_kamar>/bayar    → upload bukti pembayaran
"""

import os, io, base64
from datetime import date, datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, abort, jsonify, send_file)
from utils.auth import login_required
from models.database import get_db

try:
    import qrcode
    from qrcode.image.svg import SvgImage
    QR_OK = True
except ImportError:
    QR_OK = False

qr_bp = Blueprint('qr', __name__, url_prefix='/qr')

# ── PIN per kamar — simpan di DB atau hardcode sementara ──────────
# Idealnya kolom `pin` di tabel penghuni; sementara pakai 4 digit
# terakhir nomor HP penghuni. Fallback: '1234'.
def _get_pin(nomor_kamar):
    conn = get_db()
    row = conn.execute(
        "SELECT no_hp FROM penghuni WHERE nomor_kamar=? AND aktif=1",
        (nomor_kamar,)
    ).fetchone()
    conn.close()
    if row and row['no_hp']:
        digits = ''.join(filter(str.isdigit, row['no_hp']))
        return digits[-4:] if len(digits) >= 4 else '1234'
    return '1234'

def _portal_authed(nomor_kamar):
    return session.get(f'qr_auth_{nomor_kamar}') == True

def _base_url():
    return request.host_url.rstrip('/')


# ── Admin: generate semua QR ──────────────────────────────────────
@qr_bp.route('/admin')
@login_required
def admin():
    conn = get_db()
    penghuni_list = conn.execute(
        "SELECT id, nama, nomor_kamar, no_hp FROM penghuni WHERE aktif=1 ORDER BY nomor_kamar"
    ).fetchall()
    conn.close()

    kamar_qr = []
    for p in penghuni_list:
        url = f"{_base_url()}/qr/{p['nomor_kamar']}"
        pin = _get_pin(p['nomor_kamar'])
        kamar_qr.append({
            'nomor_kamar': p['nomor_kamar'],
            'nama':        p['nama'],
            'pin':         pin,
            'url':         url,
        })

    return render_template('qr/admin.html', kamar_qr=kamar_qr, base_url=_base_url())


# ── QR image endpoint (PNG via qrcode) ───────────────────────────
@qr_bp.route('/image/<nomor_kamar>')
def qr_image(nomor_kamar):
    if not QR_OK:
        abort(501)
    url = f"{_base_url()}/qr/{nomor_kamar}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png',
                     download_name=f'qr-kamar-{nomor_kamar}.png')


# ── Landing PIN ───────────────────────────────────────────────────
@qr_bp.route('/<nomor_kamar>', methods=['GET', 'POST'])
def pin_page(nomor_kamar):
    # Cek penghuni ada
    conn = get_db()
    p = conn.execute(
        "SELECT nama, nomor_kamar, no_hp FROM penghuni WHERE nomor_kamar=? AND aktif=1",
        (nomor_kamar,)
    ).fetchone()
    conn.close()
    if not p:
        abort(404)

    error = None
    if request.method == 'POST':
        pin_input = request.form.get('pin', '').strip()
        if pin_input == _get_pin(nomor_kamar):
            session[f'qr_auth_{nomor_kamar}'] = True
            return redirect(url_for('qr.portal', nomor_kamar=nomor_kamar))
        error = 'PIN salah. Coba lagi.'

    return render_template('qr/pin.html',
                           nomor_kamar=nomor_kamar,
                           nama=p['nama'],
                           error=error)


# ── Portal utama ──────────────────────────────────────────────────
@qr_bp.route('/<nomor_kamar>/portal')
def portal(nomor_kamar):
    if not _portal_authed(nomor_kamar):
        return redirect(url_for('qr.pin_page', nomor_kamar=nomor_kamar))

    conn = get_db()
    bulan_ini = date.today().strftime('%Y-%m')

    p = conn.execute(
        "SELECT * FROM penghuni WHERE nomor_kamar=? AND aktif=1", (nomor_kamar,)
    ).fetchone()
    if not p:
        abort(404)
    p = dict(p)

    # Tagihan bulan ini
    tagihan = conn.execute("""
        SELECT t.*, COALESCE(SUM(pb.jumlah_bayar),0) AS total_bayar
        FROM tagihan t
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE t.penghuni_id=? AND t.bulan=?
        GROUP BY t.id
    """, (p['id'], bulan_ini)).fetchone()
    tagihan = dict(tagihan) if tagihan else None
    if tagihan:
        tagihan['sisa'] = tagihan['jumlah'] - tagihan['total_bayar']

    # Tunggakan (belum lunas selain bulan ini)
    tunggakan = conn.execute("""
        SELECT t.bulan, t.jumlah, COALESCE(SUM(pb.jumlah_bayar),0) AS total_bayar
        FROM tagihan t
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE t.penghuni_id=? AND t.status IN ('belum','sebagian') AND t.bulan != ?
        GROUP BY t.id ORDER BY t.bulan DESC
    """, (p['id'], bulan_ini)).fetchall()
    tunggakan = [dict(r) for r in tunggakan]

    # Komplain aktif
    komplain_aktif = conn.execute("""
        SELECT * FROM komplain
        WHERE nomor_kamar=? AND status NOT IN ('selesai','ditutup')
        ORDER BY created_at DESC LIMIT 5
    """, (nomor_kamar,)).fetchall()

    # Info admin (ambil dari tabel admin atau hardcode)
    admin_info = conn.execute("SELECT * FROM admin LIMIT 1").fetchone()
    wa_admin = dict(admin_info)['no_hp'] if admin_info and 'no_hp' in admin_info.keys() else '08159959605'

    conn.close()
    return render_template('qr/portal.html',
                           penghuni=p,
                           tagihan=tagihan,
                           tunggakan=tunggakan,
                           komplain_aktif=[dict(r) for r in komplain_aktif],
                           wa_admin=wa_admin,
                           bulan_ini=bulan_ini,
                           nomor_kamar=nomor_kamar)


# ── Submit komplain ───────────────────────────────────────────────
@qr_bp.route('/<nomor_kamar>/komplain', methods=['POST'])
def submit_komplain(nomor_kamar):
    if not _portal_authed(nomor_kamar):
        abort(403)

    conn = get_db()
    p = conn.execute(
        "SELECT nama, no_hp FROM penghuni WHERE nomor_kamar=? AND aktif=1", (nomor_kamar,)
    ).fetchone()

    judul     = request.form.get('judul', '').strip()
    kategori  = request.form.get('kategori', 'lainnya')
    deskripsi = request.form.get('deskripsi', '').strip()

    if not judul or not deskripsi:
        return jsonify({'ok': False, 'msg': 'Judul dan deskripsi wajib diisi'}), 400

    conn.execute("""
        INSERT INTO komplain (nama_pelapor, nomor_kamar, no_hp, kategori, judul, deskripsi, status, prioritas)
        VALUES (?, ?, ?, ?, ?, ?, 'baru', 'normal')
    """, (p['nama'], nomor_kamar, p['no_hp'], kategori, judul, deskripsi))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ── Upload bukti pembayaran ───────────────────────────────────────
@qr_bp.route('/<nomor_kamar>/bayar', methods=['POST'])
def submit_bayar(nomor_kamar):
    if not _portal_authed(nomor_kamar):
        abort(403)

    conn = get_db()
    bulan_ini = date.today().strftime('%Y-%m')

    p = conn.execute(
        "SELECT id FROM penghuni WHERE nomor_kamar=? AND aktif=1", (nomor_kamar,)
    ).fetchone()
    tagihan = conn.execute(
        "SELECT id FROM tagihan WHERE penghuni_id=? AND bulan=?", (p['id'], bulan_ini)
    ).fetchone()

    if not tagihan:
        return jsonify({'ok': False, 'msg': 'Tagihan bulan ini tidak ditemukan'}), 404

    jumlah_bayar = request.form.get('jumlah_bayar', '0').replace('.', '').replace(',', '')
    metode       = request.form.get('metode', 'transfer')
    catatan      = request.form.get('catatan', '')

    try:
        jumlah_bayar = float(jumlah_bayar)
    except ValueError:
        return jsonify({'ok': False, 'msg': 'Jumlah tidak valid'}), 400

    # Simpan file bukti kalau ada
    bukti_file = None
    if 'bukti' in request.files:
        f = request.files['bukti']
        if f and f.filename:
            upload_dir = os.path.join('static', 'uploads', 'bukti')
            os.makedirs(upload_dir, exist_ok=True)
            ext = f.filename.rsplit('.', 1)[-1].lower()
            fname = f"bukti_{nomor_kamar}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
            f.save(os.path.join(upload_dir, fname))
            bukti_file = fname

    conn.execute("""
        INSERT INTO pembayaran (tagihan_id, penghuni_id, jumlah_bayar, metode, bukti_file, catatan, verified)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (tagihan['id'], p['id'], jumlah_bayar, metode, bukti_file, catatan))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
