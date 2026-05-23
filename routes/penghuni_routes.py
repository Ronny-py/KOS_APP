"""
routes/penghuni_routes.py
Kelola data penghuni kost.
"""
import os
import uuid
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, send_from_directory, abort)
from werkzeug.utils import secure_filename
from utils.auth import login_required
from models import penghuni_model
from datetime import date

penghuni_bp = Blueprint('penghuni', __name__, url_prefix='/penghuni')

# ─── helpers upload ──────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
UPLOAD_SUBFOLDER   = 'penghuni_docs'   # di dalam UPLOAD_FOLDER dari config


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_upload(file_obj, penghuni_id, prefix):
    """
    Simpan file ke disk, kembalikan nama file yang disimpan.
    prefix: 'ktp' | 'jaminan_masuk' | 'jaminan_keluar'
    """
    ext      = secure_filename(file_obj.filename).rsplit('.', 1)[-1].lower()
    filename = f"{prefix}_{penghuni_id}_{uuid.uuid4().hex[:8]}.{ext}"
    folder   = os.path.join(current_app.config['UPLOAD_FOLDER'], UPLOAD_SUBFOLDER)
    os.makedirs(folder, exist_ok=True)
    file_obj.save(os.path.join(folder, filename))
    return filename


def _delete_file(filename):
    if not filename:
        return
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], UPLOAD_SUBFOLDER)
    path   = os.path.join(folder, filename)
    if os.path.isfile(path):
        os.remove(path)


def _row_get(row, key, default=None):
    """Akses kolom SQLite row dengan aman — tidak error jika kolom belum ada."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


# ─── serve uploaded docs ─────────────────────────────────────────────────────

@penghuni_bp.route('/dokumen/<path:filename>')
@login_required
def serve_dokumen(filename):
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], UPLOAD_SUBFOLDER)
    return send_from_directory(folder, filename)


# ─── tagihan relevan ─────────────────────────────────────────────────────────

def _tagihan_relevan(penghuni_id_list: list) -> dict:
    from models.database import get_db
    from dateutil.relativedelta import relativedelta
    if not penghuni_id_list:
        return {}
    bulan_ini    = date.today().strftime('%Y-%m')
    bulan_depan  = (date.today().replace(day=1) + relativedelta(months=1)).strftime('%Y-%m')
    placeholders = ','.join('?' * len(penghuni_id_list))
    conn = get_db()
    rows = conn.execute(f"""
        SELECT penghuni_id, id AS tagihan_id, bulan, tanggal_jatuh_tempo, status,
               COALESCE(wa_count, 0) AS wa_count
        FROM tagihan
        WHERE bulan IN (?, ?) AND penghuni_id IN ({placeholders})
    """, [bulan_ini, bulan_depan] + penghuni_id_list).fetchall()
    conn.close()

    by_penghuni: dict = {}
    for r in rows:
        pid = r['penghuni_id']
        if pid not in by_penghuni:
            by_penghuni[pid] = {}
        by_penghuni[pid][r['bulan']] = dict(r)

    result = {}
    for pid in penghuni_id_list:
        data    = by_penghuni.get(pid, {})
        t_ini   = data.get(bulan_ini)
        t_depan = data.get(bulan_depan)
        if t_ini and t_ini['status'] == 'lunas' and t_depan:
            result[pid] = t_depan
        elif t_ini:
            result[pid] = t_ini
        elif t_depan:
            result[pid] = t_depan
    return result


# ─── routes utama ─────────────────────────────────────────────────────────────

@penghuni_bp.route('/')
@login_required
def index():
    daftar = penghuni_model.get_all_penghuni()
    ids = [p['id'] for p in daftar]
    tagihan_map = _tagihan_relevan(ids)
    today = date.today().strftime('%Y-%m-%d')
    return render_template('penghuni/index.html',
                           daftar=daftar,
                           tagihan_map=tagihan_map,
                           today=today)


@penghuni_bp.route('/tambah', methods=['GET', 'POST'])
@login_required
def tambah():
    if request.method == 'POST':
        data = {
            'nama':          request.form.get('nama', '').strip(),
            'nomor_kamar':   request.form.get('nomor_kamar', '').strip(),
            'no_hp':         request.form.get('no_hp', '').strip(),
            'email':         request.form.get('email', '').strip(),
            'tanggal_masuk': request.form.get('tanggal_masuk', '').strip() or None,
            'harga_sewa':    float(request.form.get('harga_sewa', 0) or 0),
        }
        if not data['nama'] or not data['nomor_kamar'] or not data['harga_sewa']:
            flash('Nama, nomor kamar, dan harga sewa wajib diisi.', 'danger')
        else:
            try:
                # Model mengembalikan last_insert_rowid langsung
                new_id = penghuni_model.tambah_penghuni(data)

                # Upload KTP
                ktp_file = request.files.get('foto_ktp')
                if ktp_file and ktp_file.filename and _allowed_file(ktp_file.filename):
                    fname = _save_upload(ktp_file, new_id, 'ktp')
                    penghuni_model.update_dokumen_penghuni(new_id, 'foto_ktp', fname)

                # Upload bukti transfer jaminan masuk
                jaminan_file = request.files.get('bukti_transfer_jaminan')
                if jaminan_file and jaminan_file.filename and _allowed_file(jaminan_file.filename):
                    fname = _save_upload(jaminan_file, new_id, 'jaminan_masuk')
                    penghuni_model.update_dokumen_penghuni(new_id, 'bukti_transfer_jaminan', fname)

                flash('Penghuni berhasil ditambahkan.', 'success')
                return redirect(url_for('penghuni.index'))
            except Exception as e:
                flash(f'Gagal: {e}', 'danger')
    return render_template('penghuni/form.html', mode='tambah', data={})


@penghuni_bp.route('/edit/<int:pid>', methods=['GET', 'POST'])
@login_required
def edit(pid):
    from models.database import get_db
    penghuni = penghuni_model.get_penghuni_by_id(pid)
    if not penghuni:
        flash('Penghuni tidak ditemukan.', 'danger')
        return redirect(url_for('penghuni.index'))

    # Konversi ke dict biasa agar aman diakses dengan .get()
    penghuni_dict = dict(penghuni)

    bulan_ini = date.today().strftime('%Y-%m')

    def get_tagihan():
        conn = get_db()
        row = conn.execute(
            "SELECT id, tanggal_jatuh_tempo, status FROM tagihan WHERE penghuni_id=? AND bulan=?",
            (pid, bulan_ini)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    if request.method == 'POST':
        data = {
            'nama':          request.form.get('nama', '').strip(),
            'nomor_kamar':   request.form.get('nomor_kamar', '').strip(),
            'no_hp':         request.form.get('no_hp', '').strip(),
            'email':         request.form.get('email', '').strip(),
            'tanggal_masuk': request.form.get('tanggal_masuk', '').strip() or None,
            'harga_sewa':    float(request.form.get('harga_sewa', 0) or 0),
        }
        jatuh_tempo_baru = request.form.get('tanggal_jatuh_tempo', '').strip() or None
        try:
            penghuni_model.update_penghuni(pid, data)

            # Upload KTP (replace jika ada file baru)
            ktp_file = request.files.get('foto_ktp')
            if ktp_file and ktp_file.filename and _allowed_file(ktp_file.filename):
                _delete_file(penghuni_dict.get('foto_ktp'))
                fname = _save_upload(ktp_file, pid, 'ktp')
                penghuni_model.update_dokumen_penghuni(pid, 'foto_ktp', fname)

            # Upload bukti transfer jaminan masuk
            jaminan_masuk_file = request.files.get('bukti_transfer_jaminan')
            if jaminan_masuk_file and jaminan_masuk_file.filename and _allowed_file(jaminan_masuk_file.filename):
                _delete_file(penghuni_dict.get('bukti_transfer_jaminan'))
                fname = _save_upload(jaminan_masuk_file, pid, 'jaminan_masuk')
                penghuni_model.update_dokumen_penghuni(pid, 'bukti_transfer_jaminan', fname)

            # Upload bukti pengembalian jaminan (keluar)
            jaminan_keluar_file = request.files.get('bukti_pengembalian_jaminan')
            if jaminan_keluar_file and jaminan_keluar_file.filename and _allowed_file(jaminan_keluar_file.filename):
                _delete_file(penghuni_dict.get('bukti_pengembalian_jaminan'))
                fname = _save_upload(jaminan_keluar_file, pid, 'jaminan_keluar')
                penghuni_model.update_dokumen_penghuni(pid, 'bukti_pengembalian_jaminan', fname)

            # Update jatuh tempo tagihan bulan ini jika ada
            if jatuh_tempo_baru:
                tagihan = get_tagihan()
                if tagihan:
                    conn = get_db()
                    conn.execute(
                        "UPDATE tagihan SET tanggal_jatuh_tempo=? WHERE id=?",
                        (jatuh_tempo_baru, tagihan['id'])
                    )
                    conn.commit()
                    conn.close()

            flash('Data penghuni diperbarui.', 'success')
            return redirect(url_for('penghuni.index'))
        except Exception as e:
            flash(f'Gagal: {e}', 'danger')

    tagihan = get_tagihan()
    return render_template('penghuni/form.html', mode='edit',
                           data=penghuni_dict,
                           tagihan=tagihan,
                           bulan_ini=bulan_ini)


# ─── hapus dokumen individual ────────────────────────────────────────────────

@penghuni_bp.route('/hapus-dokumen/<int:pid>/<field>')
@login_required
def hapus_dokumen(pid, field):
    allowed = {'foto_ktp', 'bukti_transfer_jaminan', 'bukti_pengembalian_jaminan'}
    if field not in allowed:
        abort(400)
    penghuni = penghuni_model.get_penghuni_by_id(pid)
    if not penghuni:
        abort(404)
    _delete_file(_row_get(penghuni, field))
    penghuni_model.hapus_dokumen_penghuni(pid, field)
    flash('Dokumen berhasil dihapus.', 'info')
    return redirect(url_for('penghuni.edit', pid=pid))


# ─── nonaktif / hapus ─────────────────────────────────────────────────────────

@penghuni_bp.route('/nonaktif/<int:pid>')
@login_required
def nonaktif(pid):
    penghuni_model.nonaktifkan_penghuni(pid)
    flash('Penghuni dinonaktifkan.', 'info')
    return redirect(url_for('penghuni.index'))


@penghuni_bp.route('/hapus/<int:pid>')
@login_required
def hapus(pid):
    penghuni = penghuni_model.get_penghuni_by_id(pid)
    if penghuni:
        for field in ('foto_ktp', 'bukti_transfer_jaminan', 'bukti_pengembalian_jaminan'):
            _delete_file(_row_get(penghuni, field))
    penghuni_model.hapus_penghuni(pid)
    flash('Penghuni dihapus.', 'info')
    return redirect(url_for('penghuni.index'))


# ─── helper pesan WA ─────────────────────────────────────────────────────────

def _buat_pesan_wa(row: dict, sisa: float, wa_count: int) -> str:
    """
    Buat teks pesan WA berdasarkan urutan pengiriman.
    row: gabungan dict penghuni + tagihan
    sisa: sisa tagihan yang belum dibayar
    wa_count: 1 = pertama, 2 = pengingat, 3+ = kustom/tegas
    """
    from utils.wa_service import buat_pesan_tagihan

    nama  = row.get('nama', '')
    kamar = row.get('nomor_kamar', '')
    jt    = row.get('tanggal_jatuh_tempo', '-')
    harga = f"Rp {int(sisa):,}".replace(',', '.')

    if wa_count == 1:
        # Pesan pertama — sudah ada di buat_pesan_tagihan, pakai yang lama
        return buat_pesan_tagihan(row, sisa=sisa)

    elif wa_count == 2:
        return (
            f"Halo {nama} 🔔\n\n"
            f"Kami ingin mengingatkan kembali bahwa tagihan sewa "
            f"kamar *{kamar}* sebesar *{harga}* "
            f"*belum kami terima* hingga saat ini.\n"
            f"Jatuh tempo: *{jt}*.\n\n"
            f"Mohon segera lakukan pembayaran agar tidak terkena denda. "
            f"Terima kasih 🙏"
        )

    else:
        # WA-3 dan seterusnya — pesan tegas, bisa Anda edit sesuai kebutuhan
        return (
            f"Halo {nama},\n\n"
            f"Ini adalah pemberitahuan *ke-{wa_count}* mengenai tagihan "
            f"sewa kamar *{kamar}* sebesar *{harga}* yang *belum dibayar*.\n"
            f"Jatuh tempo: *{jt}*.\n\n"
            f"Mohon segera hubungi kami untuk menyelesaikan pembayaran ini. "
            f"Jika tidak ada konfirmasi, kami terpaksa mengambil tindakan lebih lanjut.\n\n"
            f"Terima kasih."
        )


# ─── kirim notifikasi WhatsApp ────────────────────────────────────────────────

@penghuni_bp.route('/kirim-wa/<int:pid>')
@login_required
def kirim_wa(pid):
    from models.database import get_db
    from utils.wa_service import kirim_wa as kirim_wa_fn, buat_pesan_tagihan

    penghuni = penghuni_model.get_penghuni_by_id(pid)
    if not penghuni:
        flash('Penghuni tidak ditemukan.', 'danger')
        return redirect(url_for('penghuni.index'))

    bulan_ini = date.today().strftime('%Y-%m')
    conn = get_db()

    tagihan = conn.execute(
        "SELECT * FROM tagihan WHERE penghuni_id=? AND bulan=?",
        (pid, bulan_ini)
    ).fetchone()

    if not tagihan:
        flash(f'Tidak ada tagihan bulan ini untuk {penghuni["nama"]}.', 'warning')
        conn.close()
        return redirect(url_for('penghuni.index'))

    if tagihan['status'] == 'lunas':
        flash(f'Tagihan {penghuni["nama"]} sudah lunas.', 'info')
        conn.close()
        return redirect(url_for('penghuni.index'))

    bayar = conn.execute(
        "SELECT COALESCE(SUM(jumlah_bayar), 0) AS total FROM pembayaran WHERE tagihan_id=?",
        (tagihan['id'],)
    ).fetchone()['total']

    # Increment wa_count
    wa_count_baru = (tagihan['wa_count'] if tagihan['wa_count'] else 0) + 1
    conn.execute(
        "UPDATE tagihan SET wa_count=? WHERE id=?",
        (wa_count_baru, tagihan['id'])
    )
    conn.commit()
    conn.close()

    sisa = tagihan['jumlah'] - bayar
    row  = {**dict(penghuni), **dict(tagihan)}

    # Pilih pesan berdasarkan urutan kiriman
    pesan = _buat_pesan_wa(row, sisa, wa_count_baru)

    sukses, err = kirim_wa_fn(penghuni['no_hp'], pesan)
    if sukses:
        flash(f'✅ Notifikasi WA berhasil dikirim ke {penghuni["nama"]} (WA-{wa_count_baru}).', 'success')
    else:
        flash(f'❌ Gagal kirim WA ke {penghuni["nama"]}: {err}', 'danger')

    return redirect(url_for('penghuni.index'))
