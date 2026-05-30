"""
routes/pembayaran_publik_routes.py

Form PUBLIK — penghuni lapor pembayaran sendiri tanpa perlu login.
Validasi: nomor kamar DAN nama harus cocok persis (case-insensitive).
"""
import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models.database import get_db

pembayaran_publik_bp = Blueprint('pembayaran_publik', __name__, url_prefix='/bayar')

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXT   = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def _save_uploaded_files(files) -> list[dict]:
    saved = []
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for file in files:
        if file and file.filename and _allowed(file.filename):
            ext   = file.filename.rsplit('.', 1)[1].lower()
            fname = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, fname))
            saved.append({'filename': fname, 'original_name': file.filename})
    return saved


def _init_bukti_table(conn):
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


# ── GET: form kosong ──────────────────────────────────────────────────────────

@pembayaran_publik_bp.route('/', methods=['GET'])
def form_bayar():
    return render_template('pembayaran/form_publik.html',
                           selected_penghuni=None,
                           tagihan_list=None,
                           nomor_kamar='',
                           nama_input='')


# ── POST step 1: verifikasi nama + kamar ─────────────────────────────────────

@pembayaran_publik_bp.route('/cari', methods=['POST'])
def cari_tagihan():
    nomor_kamar = request.form.get('nomor_kamar', '').strip()
    nama_input  = request.form.get('nama', '').strip()

    if not nomor_kamar or not nama_input:
        flash('Nomor kamar dan nama wajib diisi.', 'danger')
        return render_template('pembayaran/form_publik.html',
                               selected_penghuni=None,
                               tagihan_list=None,
                               nomor_kamar=nomor_kamar,
                               nama_input=nama_input)

    conn = get_db()

    # Cocokkan nomor_kamar (exact) dan nama (case-insensitive, trim)
    penghuni = conn.execute("""
        SELECT * FROM penghuni
        WHERE aktif = 1
          AND LOWER(TRIM(nomor_kamar)) = LOWER(?)
          AND LOWER(TRIM(nama))        = LOWER(?)
    """, (nomor_kamar, nama_input)).fetchone()

    if not penghuni:
        conn.close()
        flash('Nomor kamar dan nama tidak cocok. Periksa kembali data Anda.', 'danger')
        return render_template('pembayaran/form_publik.html',
                               selected_penghuni=None,
                               tagihan_list=None,
                               nomor_kamar=nomor_kamar,
                               nama_input=nama_input)

    # Ambil tagihan aktif
    tagihan_list = conn.execute("""
        SELECT t.*,
               COALESCE((SELECT SUM(jumlah_bayar) FROM pembayaran
                          WHERE tagihan_id = t.id), 0) AS sudah_dibayar
        FROM tagihan t
        WHERE t.penghuni_id = ? AND t.status IN ('belum', 'sebagian')
        ORDER BY t.bulan DESC
    """, (penghuni['id'],)).fetchall()
    conn.close()

    if not tagihan_list:
        flash('Tidak ada tagihan aktif untuk kamar ini. Semua tagihan sudah lunas.', 'success')
        return render_template('pembayaran/form_publik.html',
                               selected_penghuni=penghuni,
                               tagihan_list=[],
                               nomor_kamar=nomor_kamar,
                               nama_input=nama_input)

    return render_template('pembayaran/form_publik.html',
                           selected_penghuni=penghuni,
                           tagihan_list=tagihan_list,
                           nomor_kamar=nomor_kamar,
                           nama_input=nama_input)


# ── POST step 2: simpan pembayaran ───────────────────────────────────────────

@pembayaran_publik_bp.route('/simpan', methods=['POST'])
def simpan_bayar():
    tagihan_id   = request.form.get('tagihan_id', '').strip()
    penghuni_id  = request.form.get('penghuni_id', '').strip()
    jumlah_bayar = float(request.form.get('jumlah_bayar', 0) or 0)
    metode       = request.form.get('metode', 'transfer')
    catatan      = request.form.get('catatan', '').strip()

    if not tagihan_id or not penghuni_id or jumlah_bayar <= 0:
        flash('Data tidak lengkap. Pastikan tagihan dan jumlah diisi.', 'danger')
        return redirect(url_for('pembayaran_publik.form_bayar'))

    files        = request.files.getlist('bukti_file')
    saved_files  = _save_uploaded_files(files)
    bukti_legacy = saved_files[0]['filename'] if saved_files else None

    conn = get_db()
    _init_bukti_table(conn)

    tagihan = conn.execute("SELECT * FROM tagihan WHERE id=?", (tagihan_id,)).fetchone()
    if not tagihan:
        conn.close()
        flash('Tagihan tidak ditemukan.', 'danger')
        return redirect(url_for('pembayaran_publik.form_bayar'))

    cur = conn.execute("""
        INSERT INTO pembayaran
            (tagihan_id, penghuni_id, jumlah_bayar, metode, bukti_file, catatan,
             tanggal_bayar, verified)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'), 0)
    """, (tagihan_id, penghuni_id, jumlah_bayar, metode, bukti_legacy, catatan))
    pembayaran_id = cur.lastrowid

    for f in saved_files:
        conn.execute(
            "INSERT INTO pembayaran_bukti (pembayaran_id, filename, original_name) VALUES (?,?,?)",
            (pembayaran_id, f['filename'], f['original_name'])
        )

    total_baru = conn.execute(
        "SELECT COALESCE(SUM(jumlah_bayar),0) AS t FROM pembayaran WHERE tagihan_id=?",
        (tagihan_id,)
    ).fetchone()['t']

    if total_baru >= tagihan['jumlah']:
        status_baru = 'lunas'
    elif total_baru > 0:
        status_baru = 'sebagian'
    else:
        status_baru = 'belum'

    conn.execute("UPDATE tagihan SET status=? WHERE id=?", (status_baru, tagihan_id))
    conn.commit()
    conn.close()

    flash('✅ Laporan pembayaran berhasil dikirim! Admin akan memverifikasi segera.', 'success')
    return redirect(url_for('pembayaran_publik.sukses'))


@pembayaran_publik_bp.route('/sukses')
def sukses():
    return render_template('pembayaran/publik_sukses.html')
