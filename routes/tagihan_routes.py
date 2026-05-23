"""
routes/tagihan_routes.py
Kelola tagihan sewa bulanan.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils.auth import login_required
from utils.format_helper import bulan_sekarang
from models import tagihan_model, penghuni_model, pembayaran_model
from models.database import get_db
from datetime import date

tagihan_bp = Blueprint('tagihan', __name__, url_prefix='/tagihan')


@tagihan_bp.route('/')
@login_required
def index():
    status = request.args.get('status', '')
    bulan  = request.args.get('bulan', '')
    daftar = tagihan_model.get_all_tagihan(status or None, bulan or None)
    return render_template('tagihan/index.html', daftar=daftar,
                           filter_status=status, filter_bulan=bulan,
                           bulan_ini=bulan_sekarang(),
                           today=date.today().strftime('%Y-%m-%d'))


@tagihan_bp.route('/tambah', methods=['GET', 'POST'])
@login_required
def tambah():
    penghuni_list = penghuni_model.get_all_penghuni(aktif_only=True)
    if request.method == 'POST':
        data = {
            'penghuni_id':          request.form.get('penghuni_id'),
            'bulan':                request.form.get('bulan', bulan_sekarang()),
            'jumlah':               float(request.form.get('jumlah', 0) or 0),
            'keterangan':           request.form.get('keterangan', '').strip(),
            'tanggal_jatuh_tempo':  request.form.get('tanggal_jatuh_tempo', '').strip() or None,
        }
        if not data['penghuni_id'] or not data['jumlah']:
            flash('Penghuni dan jumlah wajib diisi.', 'danger')
        else:
            try:
                tagihan_model.tambah_tagihan(data)
                flash('Tagihan berhasil dibuat.', 'success')
                return redirect(url_for('tagihan.index'))
            except Exception as e:
                flash(f'Gagal: {e}', 'danger')
    return render_template('tagihan/form.html', penghuni_list=penghuni_list,
                           bulan_ini=bulan_sekarang())


@tagihan_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    bulan = request.form.get('bulan', bulan_sekarang())
    count = tagihan_model.generate_tagihan_bulanan(bulan)
    flash(f'{count} tagihan baru dibuat untuk {bulan}.', 'success')
    return redirect(url_for('tagihan.index'))


@tagihan_bp.route('/detail/<int:tid>')
@login_required
def detail(tid):
    tagihan = tagihan_model.get_tagihan_by_id(tid)
    if not tagihan:
        flash('Tagihan tidak ditemukan.', 'danger')
        return redirect(url_for('tagihan.index'))

    pembayaran_list = pembayaran_model.get_pembayaran_by_tagihan(tid)
    total_dibayar   = pembayaran_model.total_dibayar(tid)
    sisa = tagihan['jumlah'] - total_dibayar

    # ── Ambil semua bukti untuk setiap pembayaran di tagihan ini ──
    bukti_map = {}
    if pembayaran_list:
        pm_ids = [pm['id'] for pm in pembayaran_list]
        conn = get_db()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pembayaran_bukti (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    pembayaran_id  INTEGER NOT NULL,
                    filename       TEXT    NOT NULL,
                    original_name  TEXT,
                    uploaded_at    TEXT    DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (pembayaran_id) REFERENCES pembayaran(id) ON DELETE CASCADE
                )
            """)
            placeholders = ','.join('?' for _ in pm_ids)
            rows = conn.execute(
                f"SELECT * FROM pembayaran_bukti WHERE pembayaran_id IN ({placeholders}) ORDER BY pembayaran_id, id",
                pm_ids
            ).fetchall()
            for b in rows:
                bukti_map.setdefault(b['pembayaran_id'], []).append(b)
        finally:
            conn.close()

    return render_template('tagihan/detail.html',
                           tagihan=tagihan,
                           pembayaran_list=pembayaran_list,
                           total_dibayar=total_dibayar,
                           sisa=sisa,
                           bukti_map=bukti_map,
                           today=date.today().strftime('%Y-%m-%d'))


@tagihan_bp.route('/hapus/<int:tid>')
@login_required
def hapus(tid):
    tagihan_model.hapus_tagihan(tid)
    flash('Tagihan dihapus.', 'info')
    return redirect(url_for('tagihan.index'))


# ── Kirim notifikasi WA manual ────────────────────────────────────────────────

@tagihan_bp.route('/kirim-wa/<int:tid>')
@login_required
def kirim_wa(tid):
    """Kirim notifikasi WA ke penghuni untuk tagihan tertentu secara manual."""
    tagihan = tagihan_model.get_tagihan_by_id(tid)
    if not tagihan:
        flash('Tagihan tidak ditemukan.', 'danger')
        return redirect(url_for('tagihan.index'))

    if tagihan['status'] == 'lunas':
        flash('Tagihan ini sudah lunas, tidak perlu notifikasi.', 'info')
        return redirect(url_for('tagihan.detail', tid=tid))

    no_hp = tagihan.get('no_hp', '')
    if not no_hp:
        flash('Penghuni tidak memiliki nomor HP yang terdaftar.', 'warning')
        return redirect(url_for('tagihan.detail', tid=tid))

    # Hitung sisa tagihan
    total_dibayar = pembayaran_model.total_dibayar(tid)
    sisa = tagihan['jumlah'] - total_dibayar

    from utils.wa_service import kirim_wa as send_wa, buat_pesan_tagihan
    pesan  = buat_pesan_tagihan(dict(tagihan), sisa=sisa)
    sukses, error = send_wa(no_hp, pesan)

    if sukses:
        # Reset notif_wa_terkirim = 0 agar scheduler tetap bisa kirim ulang
        # kalau mau tandai sudah terkirim manual, ubah ke 1
        conn = get_db()
        conn.execute(
            "UPDATE tagihan SET notif_wa_terkirim=1 WHERE id=?", (tid,)
        )
        conn.commit()
        conn.close()
        flash(f'✅ Notifikasi WA berhasil dikirim ke {tagihan["nama"]} ({no_hp}).', 'success')
    else:
        flash(f'❌ Gagal kirim WA: {error}', 'danger')

    return redirect(url_for('tagihan.detail', tid=tid))


@tagihan_bp.route('/reset-notif/<int:tid>')
@login_required
def reset_notif(tid):
    """Reset flag notif_wa_terkirim agar scheduler bisa kirim ulang."""
    conn = get_db()
    conn.execute("UPDATE tagihan SET notif_wa_terkirim=0 WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    flash('Flag notifikasi direset. Scheduler akan kirim ulang otomatis.', 'info')
    return redirect(url_for('tagihan.detail', tid=tid))
