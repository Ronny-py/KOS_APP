"""
routes/inventaris_routes.py
Kelola inventaris / aset kost:
perabotan, elektronik, perlengkapan kamar, area umum, dll.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils.auth import login_required
from models.database import get_db
from datetime import date

inventaris_bp = Blueprint('inventaris', __name__, url_prefix='/inventaris')

# Kategori barang
KATEGORI = [
    ('elektronik',   '🔌 Elektronik'),
    ('perabotan',    '🪑 Perabotan'),
    ('kamar_mandi',  '🚿 Kamar Mandi'),
    ('dapur',        '🍳 Dapur'),
    ('keamanan',     '🔒 Keamanan'),
    ('kebersihan',   '🧹 Kebersihan'),
    ('lainnya',      '📦 Lainnya'),
]

KATEGORI_MAP = {k: v for k, v in KATEGORI}

# Kondisi barang
KONDISI = [
    ('baik',     '✅ Baik'),
    ('sedang',   '⚠️ Sedang'),
    ('rusak',    '❌ Rusak'),
]

KONDISI_MAP = {k: v for k, v in KONDISI}


def _init_table():
    """Buat tabel inventaris jika belum ada."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventaris (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_barang TEXT    NOT NULL,
            jumlah      INTEGER NOT NULL DEFAULT 1,
            kategori    TEXT    NOT NULL DEFAULT 'lainnya',
            kondisi     TEXT    NOT NULL DEFAULT 'baik',
            lokasi      TEXT,
            keterangan  TEXT,
            tanggal     TEXT    NOT NULL DEFAULT (date('now','localtime')),
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()


def _get_filter_params():
    kat    = request.args.get('kategori', '')
    kondisi = request.args.get('kondisi', '')
    q      = request.args.get('q', '').strip()
    return kat, kondisi, q


# ── Routes ────────────────────────────────────────────────────────────────────

@inventaris_bp.route('/')
@login_required
def index():
    _init_table()
    kat, kondisi, q = _get_filter_params()

    conn  = get_db()

    # Query utama dengan filter
    where  = ["1=1"]
    params = []
    if kat:
        where.append("kategori = ?")
        params.append(kat)
    if kondisi:
        where.append("kondisi = ?")
        params.append(kondisi)
    if q:
        where.append("(nama_barang LIKE ? OR lokasi LIKE ? OR keterangan LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    query  = f"SELECT * FROM inventaris WHERE {' AND '.join(where)} ORDER BY kategori, nama_barang"
    daftar = conn.execute(query, params).fetchall()

    # Rekap per kategori
    rekap = conn.execute("""
        SELECT kategori, COUNT(*) AS jumlah_item, SUM(jumlah) AS total_unit
        FROM inventaris
        GROUP BY kategori
        ORDER BY total_unit DESC
    """).fetchall()

    # Rekap per kondisi
    rekap_kondisi = conn.execute("""
        SELECT kondisi, COUNT(*) AS jumlah_item, SUM(jumlah) AS total_unit
        FROM inventaris
        GROUP BY kondisi
    """).fetchall()

    total_item = conn.execute("SELECT COUNT(*) AS c FROM inventaris").fetchone()['c']
    total_unit = conn.execute("SELECT COALESCE(SUM(jumlah),0) AS c FROM inventaris").fetchone()['c']
    total_rusak = conn.execute(
        "SELECT COALESCE(SUM(jumlah),0) AS c FROM inventaris WHERE kondisi='rusak'"
    ).fetchone()['c']

    conn.close()

    return render_template('inventaris/index.html',
        daftar=daftar,
        rekap=rekap,
        rekap_kondisi=rekap_kondisi,
        total_item=total_item,
        total_unit=total_unit,
        total_rusak=total_rusak,
        filter_kat=kat,
        filter_kondisi=kondisi,
        filter_q=q,
        kategori=KATEGORI,
        kategori_map=KATEGORI_MAP,
        kondisi=KONDISI,
        kondisi_map=KONDISI_MAP,
    )


@inventaris_bp.route('/tambah', methods=['GET', 'POST'])
@login_required
def tambah():
    _init_table()
    if request.method == 'POST':
        nama    = request.form.get('nama_barang', '').strip()
        jumlah  = int(request.form.get('jumlah', 1) or 1)
        kat     = request.form.get('kategori', 'lainnya')
        kond    = request.form.get('kondisi', 'baik')
        lokasi  = request.form.get('lokasi', '').strip()
        ket     = request.form.get('keterangan', '').strip()
        tanggal = request.form.get('tanggal', date.today().isoformat())

        if not nama:
            flash('Nama barang wajib diisi.', 'danger')
        elif jumlah < 1:
            flash('Jumlah harus minimal 1.', 'danger')
        else:
            conn = get_db()
            conn.execute("""
                INSERT INTO inventaris
                    (nama_barang, jumlah, kategori, kondisi, lokasi, keterangan, tanggal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nama, jumlah, kat, kond, lokasi, ket, tanggal))
            conn.commit()
            conn.close()
            flash(f'"{nama}" berhasil ditambahkan ke inventaris.', 'success')
            return redirect(url_for('inventaris.index'))

    return render_template('inventaris/form.html',
        mode='tambah', data={},
        kategori=KATEGORI, kondisi=KONDISI,
        today=date.today().isoformat())


@inventaris_bp.route('/edit/<int:iid>', methods=['GET', 'POST'])
@login_required
def edit(iid):
    _init_table()
    conn = get_db()
    row  = conn.execute("SELECT * FROM inventaris WHERE id=?", (iid,)).fetchone()
    conn.close()
    if not row:
        flash('Data tidak ditemukan.', 'danger')
        return redirect(url_for('inventaris.index'))

    if request.method == 'POST':
        nama    = request.form.get('nama_barang', '').strip()
        jumlah  = int(request.form.get('jumlah', 1) or 1)
        kat     = request.form.get('kategori', row['kategori'])
        kond    = request.form.get('kondisi', row['kondisi'])
        lokasi  = request.form.get('lokasi', '').strip()
        ket     = request.form.get('keterangan', '').strip()
        tanggal = request.form.get('tanggal', row['tanggal'])

        if not nama:
            flash('Nama barang wajib diisi.', 'danger')
        elif jumlah < 1:
            flash('Jumlah harus minimal 1.', 'danger')
        else:
            conn = get_db()
            conn.execute("""
                UPDATE inventaris
                SET nama_barang=?, jumlah=?, kategori=?, kondisi=?,
                    lokasi=?, keterangan=?, tanggal=?
                WHERE id=?
            """, (nama, jumlah, kat, kond, lokasi, ket, tanggal, iid))
            conn.commit()
            conn.close()
            flash('Data inventaris berhasil diperbarui.', 'success')
            return redirect(url_for('inventaris.index'))

    return render_template('inventaris/form.html',
        mode='edit', data=dict(row),
        kategori=KATEGORI, kondisi=KONDISI,
        today=date.today().isoformat())


@inventaris_bp.route('/hapus/<int:iid>')
@login_required
def hapus(iid):
    _init_table()
    conn = get_db()
    row  = conn.execute("SELECT nama_barang FROM inventaris WHERE id=?", (iid,)).fetchone()
    conn.execute("DELETE FROM inventaris WHERE id=?", (iid,))
    conn.commit()
    conn.close()
    nama = row['nama_barang'] if row else 'Barang'
    flash(f'"{nama}" dihapus dari inventaris.', 'info')
    return redirect(url_for('inventaris.index'))


@inventaris_bp.route('/update-kondisi/<int:iid>/<kondisi_baru>')
@login_required
def update_kondisi(iid, kondisi_baru):
    """Shortcut update kondisi langsung dari tabel."""
    valid = {'baik', 'sedang', 'rusak'}
    if kondisi_baru not in valid:
        flash('Kondisi tidak valid.', 'danger')
        return redirect(url_for('inventaris.index'))
    _init_table()
    conn = get_db()
    conn.execute("UPDATE inventaris SET kondisi=? WHERE id=?", (kondisi_baru, iid))
    conn.commit()
    conn.close()
    flash('Kondisi barang diperbarui.', 'success')
    return redirect(url_for('inventaris.index'))
