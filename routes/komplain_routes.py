"""
routes/komplain_routes.py
Admin: lihat, tanggapi, dan buat laporan komplain.
"""
import os
import requests as req_lib
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, send_from_directory, current_app, session)
from models import komplain_model
from functools import wraps

WA_SERVER_URL = "http://localhost:3000"

STATUS_LABEL = {
    'baru':      'Baru',
    'diproses':  'Sedang Diproses',
    'selesai':   'Selesai ✅',
    'ditolak':   'Ditolak ❌',
}

def _kirim_notif_wa_komplain(row, status_baru, catatan):
    """Kirim WA ke penghuni saat admin merespons komplain."""
    if not isinstance(row, dict):
        row = dict(row)  # sqlite3.Row → dict
    no_hp = (row.get('no_hp') or '').strip()
    if not no_hp:
        return

    # Format nomor: pastikan diawali 62
    nomor = no_hp.lstrip('+').strip()
    if nomor.startswith('0'):
        nomor = '62' + nomor[1:]

    status_text = STATUS_LABEL.get(status_baru, status_baru.upper())

    pesan = (
        f"📋 *Update Komplain Anda*\n\n"
        f"Halo *{row['nama_pelapor']}*, komplain Anda telah diperbarui.\n\n"
        f"📌 *Judul:* {row['judul']}\n"
        f"🏠 *Kamar:* {row['nomor_kamar']}\n"
        f"📊 *Status:* {status_text}\n"
    )
    if catatan:
        pesan += f"\n💬 *Catatan Admin:*\n{catatan}\n"

    pesan += "\nTerima kasih atas kesabaran Anda. 🙏"

    try:
        resp = req_lib.post(
            f"{WA_SERVER_URL}/api/send-message",
            json={"number": nomor, "message": pesan},
            timeout=5,
        )
        if resp.ok and resp.json().get('success'):
            current_app.logger.info(f"Notif WA komplain terkirim ke {nomor}")
        else:
            current_app.logger.warning(f"WA gagal: {resp.text}")
    except Exception as e:
        current_app.logger.warning(f"WA server tidak terjangkau: {e}")

komplain_bp = Blueprint('komplain', __name__, url_prefix='/komplain')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Daftar Komplain ───────────────────────────────────────────────────────────
@komplain_bp.route('/')
@login_required
def index():
    status = request.args.get('status', '')
    search = request.args.get('q', '')
    now    = datetime.now()
    bulan  = int(request.args.get('bulan', now.month))
    tahun  = int(request.args.get('tahun', now.year))

    daftar = komplain_model.get_all(
        status=status or None,
        bulan=bulan if request.args.get('bulan') else None,
        tahun=tahun if request.args.get('tahun') else None,
        search=search or None,
    )

    # Hitung badge tiap status
    semua  = komplain_model.get_all()
    counts = {s: sum(1 for r in semua if r['status']==s)
              for s,_ in komplain_model.STATUS_LIST}
    counts['semua'] = len(semua)

    return render_template('komplain/index.html',
        daftar=daftar,
        counts=counts,
        status_filter=status,
        search=search,
        bulan=bulan, tahun=tahun,
        STATUS_LIST=komplain_model.STATUS_LIST,
        KATEGORI_LIST=komplain_model.KATEGORI_LIST,
        PRIORITAS_LIST=komplain_model.PRIORITAS_LIST,
    )


# ── Detail & Tanggapi ─────────────────────────────────────────────────────────
@komplain_bp.route('/<int:kid>')
@login_required
def detail(kid):
    row = komplain_model.get_by_id(kid)
    if not row:
        flash('Komplain tidak ditemukan.', 'danger')
        return redirect(url_for('komplain.index'))
    return render_template('komplain/detail.html',
        row=row,
        STATUS_LIST=komplain_model.STATUS_LIST,
        PRIORITAS_LIST=komplain_model.PRIORITAS_LIST,
    )


@komplain_bp.route('/<int:kid>/tanggapi', methods=['POST'])
@login_required
def tanggapi(kid):
    status_lama = None
    row = komplain_model.get_by_id(kid)
    if row:
        status_lama = row['status']

    status  = request.form.get('status', 'diproses')
    catatan = request.form.get('catatan_admin', '').strip()
    komplain_model.update_status(kid, status, catatan or None)

    # Kirim notif WA ke penghuni jika status berubah atau ada catatan baru
    if row and (status != status_lama or catatan):
        _kirim_notif_wa_komplain(row, status, catatan)
        flash('Tanggapan berhasil disimpan dan notifikasi WA dikirim ke penghuni.', 'success')
    else:
        flash('Tanggapan berhasil disimpan.', 'success')

    return redirect(url_for('komplain.detail', kid=kid))


@komplain_bp.route('/<int:kid>/prioritas', methods=['POST'])
@login_required
def set_prioritas(kid):
    prioritas = request.form.get('prioritas', 'normal')
    komplain_model.update_prioritas(kid, prioritas)
    return redirect(url_for('komplain.detail', kid=kid))


@komplain_bp.route('/<int:kid>/hapus', methods=['POST'])
@login_required
def hapus(kid):
    foto = komplain_model.hapus(kid)
    if foto:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], foto))
        except Exception:
            pass
    flash('Komplain dihapus.', 'success')
    return redirect(url_for('komplain.index'))


# ── Serve foto ────────────────────────────────────────────────────────────────
@komplain_bp.route('/foto/<path:filename>')
@login_required
def serve_foto(filename):
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'komplain')
    return send_from_directory(folder, filename)


# ── Laporan ───────────────────────────────────────────────────────────────────
@komplain_bp.route('/laporan')
@login_required
def laporan():
    now   = datetime.now()
    bulan = int(request.args.get('bulan', now.month))
    tahun = int(request.args.get('tahun', now.year))

    stats     = komplain_model.stats_bulan(bulan, tahun)
    per_kat   = komplain_model.stats_per_kategori(bulan, tahun)
    avg_hari  = komplain_model.avg_selesai_hari(bulan, tahun)
    daftar    = komplain_model.get_all(bulan=bulan, tahun=tahun)

    BULAN_NAMA = ['','Januari','Februari','Maret','April','Mei','Juni',
                  'Juli','Agustus','September','Oktober','November','Desember']

    return render_template('komplain/laporan.html',
        bulan=bulan, tahun=tahun,
        bulan_nama=BULAN_NAMA[bulan],
        stats=stats,
        per_kat=per_kat,
        avg_hari=avg_hari,
        daftar=daftar,
        KATEGORI_LIST=komplain_model.KATEGORI_LIST,
        STATUS_LIST=komplain_model.STATUS_LIST,
        BULAN_NAMA=BULAN_NAMA,
    )
