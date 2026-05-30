"""
routes/pembayaran_routes.py
Catat dan kelola pembayaran tagihan.
Mendukung upload MULTIPLE bukti transfer per pembayaran.
"""
import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils.auth import login_required
from models import tagihan_model, pembayaran_model
from models.database import get_db
from datetime import date
from dateutil.relativedelta import relativedelta

pembayaran_bp = Blueprint('pembayaran', __name__, url_prefix='/pembayaran')

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXT   = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def _init_bukti_table():
    """Pastikan tabel pembayaran_bukti sudah ada (migrasi otomatis)."""
    conn = get_db()
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
    conn.commit()
    conn.close()


def _save_uploaded_files(files) -> list[dict]:
    """
    Simpan daftar file yang di-upload.
    Kembalikan list of dict: {filename, original_name}
    """
    saved = []
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for file in files:
        if file and file.filename and _allowed(file.filename):
            ext      = file.filename.rsplit('.', 1)[1].lower()
            fname    = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, fname))
            saved.append({'filename': fname, 'original_name': file.filename})
    return saved


def _insert_bukti(conn, pembayaran_id: int, saved_files: list[dict]):
    """Masukkan baris ke pembayaran_bukti untuk setiap file."""
    for f in saved_files:
        conn.execute(
            """INSERT INTO pembayaran_bukti (pembayaran_id, filename, original_name)
               VALUES (?, ?, ?)""",
            (pembayaran_id, f['filename'], f['original_name'])
        )


def get_bukti_by_pembayaran(pembayaran_id: int) -> list:
    """Ambil semua bukti untuk satu pembayaran."""
    _init_bukti_table()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pembayaran_bukti WHERE pembayaran_id=? ORDER BY id",
        (pembayaran_id,)
    ).fetchall()
    conn.close()
    return rows


def _buat_tagihan_bulan_berikut(tagihan: dict):
    """
    Setelah pembayaran dicatat, buat tagihan bulan depan jika belum ada.

    Tanggal jatuh tempo = tanggal masuk penghuni (hanya ambil hari-nya),
    tapi bulan & tahun mengikuti bulan tagihan berikutnya.

    Contoh: penghuni masuk 15 Maret, tagihan berikutnya Juli 2025
            -> jatuh tempo = 2025-07-15

    Fallback (jika tanggal_masuk tidak tersedia): hari terakhir bulan tagihan.
    """
    import calendar
    from datetime import datetime

    bulan_skrg = tagihan['bulan']
    dt_bulan   = datetime.strptime(bulan_skrg + '-01', '%Y-%m-%d')
    bulan_next = (dt_bulan + relativedelta(months=1)).strftime('%Y-%m')
    year_next, month_next = map(int, bulan_next.split('-'))

    conn = get_db()

    # Ambil tanggal_masuk + harga_sewa penghuni dalam satu query
    p = conn.execute(
        "SELECT harga_sewa, tanggal_masuk FROM penghuni WHERE id=?",
        (tagihan['penghuni_id'],)
    ).fetchone()

    if p and p['tanggal_masuk']:
        try:
            # Gunakan hari dari tanggal_masuk sebagai hari jatuh tempo
            tgl_masuk = datetime.strptime(str(p['tanggal_masuk'])[:10], '%Y-%m-%d')
            hari_jt   = tgl_masuk.day
            # Clamp ke hari maksimum bulan berikutnya (misal masuk tgl 31, bulan 30 hari)
            hari_max  = calendar.monthrange(year_next, month_next)[1]
            hari_jt   = min(hari_jt, hari_max)
            jt_next   = f"{year_next:04d}-{month_next:02d}-{hari_jt:02d}"
        except (ValueError, TypeError):
            # tanggal_masuk tidak bisa di-parse -> fallback hari terakhir bulan
            hari_max = calendar.monthrange(year_next, month_next)[1]
            jt_next  = f"{year_next:04d}-{month_next:02d}-{hari_max:02d}"
    else:
        # Tidak ada data penghuni / tanggal_masuk -> fallback hari terakhir bulan
        hari_max = calendar.monthrange(year_next, month_next)[1]
        jt_next  = f"{year_next:04d}-{month_next:02d}-{hari_max:02d}"

    harga = p['harga_sewa'] if p else tagihan['jumlah']

    existing = conn.execute(
        "SELECT id FROM tagihan WHERE penghuni_id=? AND bulan=?",
        (tagihan['penghuni_id'], bulan_next)
    ).fetchone()

    if not existing:
        conn.execute("""
            INSERT INTO tagihan (penghuni_id, bulan, jumlah, keterangan, status, tanggal_jatuh_tempo)
            VALUES (?, ?, ?, 'Tagihan sewa bulanan', 'belum', ?)
        """, (tagihan['penghuni_id'], bulan_next, harga, jt_next))
    else:
        conn.execute(
            "UPDATE tagihan SET tanggal_jatuh_tempo=? WHERE id=?",
            (jt_next, existing['id'])
        )

    conn.commit()
    conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@pembayaran_bp.route('/tambah/<int:tagihan_id>', methods=['GET', 'POST'])
@login_required
def tambah(tagihan_id):
    _init_bukti_table()
    tagihan = tagihan_model.get_tagihan_by_id(tagihan_id)
    if not tagihan:
        flash('Tagihan tidak ditemukan.', 'danger')
        return redirect(url_for('tagihan.index'))

    total_dibayar = pembayaran_model.total_dibayar(tagihan_id)
    sisa = tagihan['jumlah'] - total_dibayar

    if request.method == 'POST':
        jumlah_bayar = float(request.form.get('jumlah_bayar', 0) or 0)
        metode       = request.form.get('metode', 'transfer')
        catatan      = request.form.get('catatan', '').strip()

        # ── Handle MULTIPLE file uploads ──────────────────────────────────
        files       = request.files.getlist('bukti_file')   # getlist untuk multiple
        saved_files = _save_uploaded_files(files)

        # Tetap isi kolom bukti_file lama dengan file pertama (backward compat)
        bukti_file_legacy = saved_files[0]['filename'] if saved_files else None

        if jumlah_bayar <= 0:
            flash('Jumlah bayar harus lebih dari 0.', 'danger')
        else:
            conn = get_db()
            cur = conn.execute("""
                INSERT INTO pembayaran
                    (tagihan_id, penghuni_id, jumlah_bayar, metode, bukti_file, catatan, tanggal_bayar)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            """, (tagihan_id, tagihan['penghuni_id'], jumlah_bayar,
                  metode, bukti_file_legacy, catatan))
            pembayaran_id = cur.lastrowid

            # Simpan setiap bukti ke tabel pembayaran_bukti
            _insert_bukti(conn, pembayaran_id, saved_files)

            # Update status tagihan
            total_baru = total_dibayar + jumlah_bayar
            if total_baru >= tagihan['jumlah']:
                status_baru = 'lunas'
            elif total_baru > 0:
                status_baru = 'sebagian'
            else:
                status_baru = 'belum'
            conn.execute("UPDATE tagihan SET status=? WHERE id=?", (status_baru, tagihan_id))
            # Reset wa_count karena penghuni sudah melakukan pembayaran
            conn.execute("UPDATE tagihan SET wa_count=0 WHERE id=?", (tagihan_id,))
            conn.commit()
            conn.close()

            _buat_tagihan_bulan_berikut(dict(tagihan))

            n = len(saved_files)
            pesan_bukti = f" dengan {n} bukti transfer" if n > 0 else ""
            flash(f'Pembayaran berhasil dicatat{pesan_bukti}.', 'success')
            return redirect(url_for('tagihan.detail', tid=tagihan_id))

    return render_template('pembayaran/form.html', tagihan=tagihan, sisa=sisa)


@pembayaran_bp.route('/hapus-bukti/<int:bukti_id>/<int:pembayaran_id>')
@login_required
def hapus_bukti(bukti_id, pembayaran_id):
    """Hapus satu file bukti dari pembayaran yang sudah ada."""
    _init_bukti_table()
    conn = get_db()
    row = conn.execute(
        "SELECT filename FROM pembayaran_bukti WHERE id=? AND pembayaran_id=?",
        (bukti_id, pembayaran_id)
    ).fetchone()
    if row:
        # Hapus file fisik
        fpath = os.path.join(UPLOAD_FOLDER, row['filename'])
        if os.path.exists(fpath):
            os.remove(fpath)
        conn.execute("DELETE FROM pembayaran_bukti WHERE id=?", (bukti_id,))
        conn.commit()
        flash('Bukti berhasil dihapus.', 'info')
    conn.close()
    # Redirect ke detail tagihan; ambil tagihan_id dari pembayaran
    conn2 = get_db()
    pm = conn2.execute("SELECT tagihan_id FROM pembayaran WHERE id=?", (pembayaran_id,)).fetchone()
    conn2.close()
    return redirect(url_for('tagihan.detail', tid=pm['tagihan_id']) if pm else url_for('tagihan.index'))


@pembayaran_bp.route('/tambah-bukti/<int:pembayaran_id>', methods=['POST'])
@login_required
def tambah_bukti(pembayaran_id):
    """Tambah bukti ke pembayaran yang sudah ada."""
    _init_bukti_table()
    files       = request.files.getlist('bukti_file')
    saved_files = _save_uploaded_files(files)

    if not saved_files:
        flash('Tidak ada file valid yang di-upload.', 'warning')
    else:
        conn = get_db()
        _insert_bukti(conn, pembayaran_id, saved_files)
        conn.commit()
        conn.close()
        flash(f'{len(saved_files)} bukti berhasil ditambahkan.', 'success')

    conn2 = get_db()
    pm = conn2.execute("SELECT tagihan_id FROM pembayaran WHERE id=?", (pembayaran_id,)).fetchone()
    conn2.close()
    return redirect(url_for('tagihan.detail', tid=pm['tagihan_id']) if pm else url_for('tagihan.index'))


@pembayaran_bp.route('/verifikasi/<int:pid>/<int:status>')
@login_required
def verifikasi(pid, status):
    conn = get_db()
    conn.execute("UPDATE pembayaran SET verified=? WHERE id=?", (status, pid))
    conn.commit()
    row = conn.execute("SELECT tagihan_id FROM pembayaran WHERE id=?", (pid,)).fetchone()
    conn.close()
    flash('Status verifikasi diperbarui.', 'success')
    return redirect(url_for('tagihan.detail', tid=row['tagihan_id']) if row else url_for('tagihan.index'))


@pembayaran_bp.route('/hapus/<int:pid>')
@login_required
def hapus(pid):
    conn = get_db()
    row = conn.execute(
        "SELECT tagihan_id, jumlah_bayar FROM pembayaran WHERE id=?", (pid,)
    ).fetchone()
    if row:
        # Hapus file-file bukti fisik
        _init_bukti_table()
        bukti_rows = conn.execute(
            "SELECT filename FROM pembayaran_bukti WHERE pembayaran_id=?", (pid,)
        ).fetchall()
        for b in bukti_rows:
            fpath = os.path.join(UPLOAD_FOLDER, b['filename'])
            if os.path.exists(fpath):
                os.remove(fpath)
        conn.execute("DELETE FROM pembayaran_bukti WHERE pembayaran_id=?", (pid,))

        conn.execute("DELETE FROM pembayaran WHERE id=?", (pid,))
        total = conn.execute(
            "SELECT COALESCE(SUM(jumlah_bayar),0) AS t FROM pembayaran WHERE tagihan_id=?",
            (row['tagihan_id'],)
        ).fetchone()['t']
        tagihan = conn.execute("SELECT jumlah FROM tagihan WHERE id=?", (row['tagihan_id'],)).fetchone()
        if tagihan:
            if total <= 0:
                status = 'belum'
            elif total >= tagihan['jumlah']:
                status = 'lunas'
            else:
                status = 'sebagian'
            conn.execute("UPDATE tagihan SET status=? WHERE id=?", (status, row['tagihan_id']))
            # Reset wa_count jika status kembali ke belum bayar
            if status == 'belum':
                conn.execute("UPDATE tagihan SET wa_count=0 WHERE id=?", (row['tagihan_id'],))
        conn.commit()
    conn.close()
    flash('Pembayaran dihapus.', 'info')
    return redirect(url_for('tagihan.detail', tid=row['tagihan_id']) if row else url_for('tagihan.index'))


@pembayaran_bp.route('/')
@login_required
def index():
    _init_bukti_table()
    conn = get_db()
    daftar = conn.execute("""
        SELECT pm.*, p.nama, p.nomor_kamar, t.bulan, t.jumlah AS jumlah_tagihan
        FROM pembayaran pm
        JOIN tagihan  t ON pm.tagihan_id  = t.id
        JOIN penghuni p ON pm.penghuni_id = p.id
        ORDER BY pm.tanggal_bayar DESC
    """).fetchall()

    # Ambil semua bukti sekaligus, group by pembayaran_id
    all_bukti = conn.execute(
        "SELECT * FROM pembayaran_bukti ORDER BY pembayaran_id, id"
    ).fetchall()
    conn.close()

    # Buat map: pembayaran_id -> [bukti, ...]
    bukti_map = {}
    for b in all_bukti:
        bukti_map.setdefault(b['pembayaran_id'], []).append(b)

    return render_template('pembayaran/index.html', daftar=daftar, bukti_map=bukti_map)
