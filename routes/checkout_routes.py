"""
routes/checkout_routes.py
Fitur check-out penghuni — admin only.
"""
import os, uuid
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify, session, current_app, send_from_directory)
from functools import wraps
from models import checkout_model

checkout_bp = Blueprint('checkout', __name__, url_prefix='/checkout')

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'pdf'}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _save_bukti(file):
    if not file or file.filename == '':
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return None
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'checkout')
    os.makedirs(folder, exist_ok=True)
    fname = f"checkout_{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(folder, fname))
    return f"checkout/{fname}"


# ── Halaman utama checkout ────────────────────────────────────────────────────
@checkout_bp.route('/')
@login_required
def index():
    from models.database import get_db
    penghuni_list = checkout_model.get_penghuni_aktif()
    history       = checkout_model.get_history(30)

    # Riwayat check-in: semua penghuni (aktif & nonaktif), urut terbaru
    conn = get_db()
    history_checkin = conn.execute("""
        SELECT id, nama, nomor_kamar, no_hp, tanggal_masuk, harga_sewa, aktif
        FROM penghuni
        ORDER BY tanggal_masuk DESC, id DESC
        LIMIT 50
    """).fetchall()
    history_checkin = [dict(r) for r in history_checkin]
    conn.close()

    tab = request.args.get('tab', 'checkout')
    return render_template('checkout/index.html',
                           penghuni_list=penghuni_list,
                           history=history,
                           history_checkin=history_checkin,
                           tab=tab)


# ── Proses check-in (tambah penghuni baru) ────────────────────────────────────
@checkout_bp.route('/checkin', methods=['POST'])
@login_required
def proses_checkin():
    from models.database import get_db
    nama          = request.form.get('nama', '').strip()
    nomor_kamar   = request.form.get('nomor_kamar', '').strip()
    no_hp         = request.form.get('no_hp', '').strip()
    email         = request.form.get('email', '').strip()
    tanggal_masuk = request.form.get('tanggal_masuk', '').strip()
    harga_sewa    = request.form.get('harga_sewa', '0').replace('.', '').replace(',', '')
    deposit       = request.form.get('deposit', '0').replace('.', '').replace(',', '')
    keterangan    = request.form.get('keterangan', '').strip()

    if not nama or not nomor_kamar or not tanggal_masuk:
        flash('Nama, nomor kamar, dan tanggal masuk wajib diisi.', 'danger')
        return redirect(url_for('checkout.index', tab='checkin'))

    try:
        harga_sewa = float(harga_sewa)
        deposit    = float(deposit)
    except ValueError:
        flash('Harga sewa / deposit tidak valid.', 'danger')
        return redirect(url_for('checkout.index', tab='checkin'))

    conn = get_db()

    # Cek kamar sudah ditempati penghuni aktif
    aktif = conn.execute(
        "SELECT id FROM penghuni WHERE nomor_kamar=? AND aktif=1", (nomor_kamar,)
    ).fetchone()
    if aktif:
        conn.close()
        flash(f'Kamar {nomor_kamar} sudah ditempati penghuni aktif.', 'danger')
        return redirect(url_for('checkout.index', tab='checkin'))

    # Cek apakah kamar ini pernah ada di DB (sudah checkout sebelumnya)
    # Ambil record nonaktif terakhir untuk kamar ini
    reuse = conn.execute("""
        SELECT id FROM penghuni
        WHERE nomor_kamar=? AND aktif=0
        ORDER BY id DESC LIMIT 1
    """, (nomor_kamar,)).fetchone()

    if reuse:
        # Reuse record lama — update, jangan INSERT baru
        conn.execute("""
            UPDATE penghuni
            SET nama=?, no_hp=?, email=?, tanggal_masuk=?,
                harga_sewa=?, deposit=?, keterangan=?,
                aktif=1, tanggal_keluar=NULL,
                bukti_pengembalian_jaminan=NULL
            WHERE id=?
        """, (nama, no_hp or None, email or None, tanggal_masuk,
              harga_sewa, deposit, keterangan or None, reuse['id']))
        conn.commit()
        conn.close()
        flash(f'✅ Check-in berhasil! {nama} — Kamar {nomor_kamar} diaktifkan kembali (data lama diperbarui).', 'success')
    else:
        # Kamar benar-benar baru, INSERT
        conn.execute("""
            INSERT INTO penghuni (nama, nomor_kamar, no_hp, email, tanggal_masuk,
                                  harga_sewa, deposit, keterangan, aktif)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (nama, nomor_kamar, no_hp or None, email or None, tanggal_masuk,
              harga_sewa, deposit, keterangan or None))
        conn.commit()
        conn.close()
        flash(f'✅ Check-in berhasil! {nama} — Kamar {nomor_kamar} sudah terdaftar.', 'success')

    return redirect(url_for('checkout.index', tab='checkin'))


# ── API: detail penghuni untuk preview sebelum checkout ───────────────────────
@checkout_bp.route('/api/preview/<int:pid>')
@login_required
def preview(pid):
    penghuni = checkout_model.get_penghuni_by_id(pid)
    if not penghuni:
        return jsonify(ok=False, msg='Penghuni tidak ditemukan'), 404

    tagihan_list  = checkout_model.get_tagihan_belum_lunas(pid)
    tagihan_sisa  = checkout_model.get_total_belum_lunas(pid)
    deposit       = float(penghuni['deposit'] or 0)
    today         = datetime.now().strftime('%Y-%m-%d')
    lama          = checkout_model.hitung_lama_tinggal(
                        penghuni['tanggal_masuk'] or today, today)

    return jsonify(
        ok=True,
        nama=penghuni['nama'],
        nomor_kamar=penghuni['nomor_kamar'],
        tanggal_masuk=penghuni['tanggal_masuk'],
        harga_sewa=penghuni['harga_sewa'],
        deposit=deposit,
        tagihan_sisa=tagihan_sisa,
        lama_hari=lama,
        tagihan_list=[
            {'bulan': t['bulan'], 'jumlah': t['jumlah'], 'sudah_bayar': t['sudah_bayar']}
            for t in tagihan_list
        ],
        estimasi_kembali=max(0, deposit - tagihan_sisa),
    )


# ── Proses checkout ───────────────────────────────────────────────────────────
@checkout_bp.route('/proses', methods=['POST'])
@login_required
def proses():
    penghuni_id        = request.form.get('penghuni_id', type=int)
    tanggal_keluar     = request.form.get('tanggal_keluar', '').strip()
    kondisi_kamar      = request.form.get('kondisi_kamar', 'baik').strip()
    potongan           = request.form.get('potongan_kerusakan', 0, type=float)
    ket_potongan       = request.form.get('keterangan_potongan', '').strip()
    catatan            = request.form.get('catatan', '').strip()
    bukti_path         = _save_bukti(request.files.get('bukti_pengembalian'))
    admin_nama         = session.get('admin_nama', 'Admin')

    if not penghuni_id or not tanggal_keluar:
        flash('Penghuni dan tanggal keluar wajib diisi.', 'danger')
        return redirect(url_for('checkout.index'))

    try:
        dikembalikan = checkout_model.proses_checkout(
            penghuni_id, tanggal_keluar, kondisi_kamar,
            potongan, ket_potongan or None,
            catatan or None, bukti_path, admin_nama
        )
        flash(
            f'✅ Check-out berhasil! Deposit dikembalikan: '
            f'Rp {dikembalikan:,.0f}'.replace(',', '.'),
            'success'
        )
    except Exception as e:
        current_app.logger.error(f'[checkout] error: {e}')
        flash(f'❌ Gagal proses checkout: {e}', 'danger')

    return redirect(url_for('checkout.index'))


# ── Detail history checkout ───────────────────────────────────────────────────
@checkout_bp.route('/history/<int:cid>')
@login_required
def detail(cid):
    row = checkout_model.get_checkout_by_id(cid)
    if not row:
        flash('Data checkout tidak ditemukan.', 'danger')
        return redirect(url_for('checkout.index'))
    return render_template('checkout/detail.html', row=row)


# ── Serve file bukti ──────────────────────────────────────────────────────────
@checkout_bp.route('/bukti/<path:filename>')
@login_required
def serve_bukti(filename):
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'checkout')
    return send_from_directory(folder, filename)
