"""
routes/pengeluaran_routes.py
Kelola pengeluaran operasional kost:
cuci AC, perbaikan, listrik, gaji, sampah, beli barang, dll.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils.auth import login_required
from models.database import get_db
from datetime import date

pengeluaran_bp = Blueprint('pengeluaran', __name__, url_prefix='/pengeluaran')

# Kategori pengeluaran yang tersedia
KATEGORI = [
    ('listrik',     '⚡ Listrik'),
    ('air',         '💧 Air / PDAM'),
    ('sampah',      '🗑️ Sampah & Kebersihan'),
    ('keamanan',    '🔒 Keamanan / Satpam'),
    ('gaji',        '👷 Gaji Karyawan'),
    ('cuci_ac',     '❄️ Cuci / Service AC'),
    ('perbaikan',   '🔧 Perbaikan Kamar / Fasilitas'),
    ('beli_barang', '🛒 Beli Barang / Perlengkapan'),
    ('internet',    '🌐 Internet / Wi-Fi'),
    ('pajak',       '🏛️ Pajak & Administrasi'),
    ('lainnya',     '🔄 Kembali Deposit'),
]

KATEGORI_MAP = {k: v for k, v in KATEGORI}


def _init_table():
    """Buat tabel pengeluaran jika belum ada (migrasi otomatis)."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pengeluaran (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal     TEXT    NOT NULL,
            kategori    TEXT    NOT NULL,
            keterangan  TEXT    NOT NULL,
            jumlah      REAL    NOT NULL DEFAULT 0,
            dibayar_ke  TEXT,
            catatan     TEXT,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()


def _get_filter_params():
    now   = date.today()
    bulan = request.args.get('bulan', f"{now.year}-{now.month:02d}")
    kat   = request.args.get('kategori', '')
    return bulan, kat


# ── Routes ────────────────────────────────────────────────────────────────────

@pengeluaran_bp.route('/')
@login_required
def index():
    _init_table()
    bulan, kat = _get_filter_params()

    conn  = get_db()

    # Ambil daftar bulan yang tersedia untuk filter
    bulan_list = conn.execute(
        "SELECT DISTINCT substr(tanggal,1,7) AS bln FROM pengeluaran ORDER BY bln DESC"
    ).fetchall()
    bulan_list = [r['bln'] for r in bulan_list]

    # Query utama
    query  = "SELECT * FROM pengeluaran WHERE substr(tanggal,1,7)=?"
    params = [bulan]
    if kat:
        query  += " AND kategori=?"
        params.append(kat)
    query += " ORDER BY tanggal DESC, id DESC"

    daftar = conn.execute(query, params).fetchall()

    # Total
    total = sum(r['jumlah'] for r in daftar)

    # Rekap per kategori untuk bulan ini
    rekap = conn.execute("""
        SELECT kategori, SUM(jumlah) AS total
        FROM pengeluaran
        WHERE substr(tanggal,1,7)=?
        GROUP BY kategori
        ORDER BY total DESC
    """, (bulan,)).fetchall()

    conn.close()

    return render_template('pengeluaran/index.html',
        daftar=daftar, total=total, rekap=rekap,
        bulan=bulan, bulan_list=bulan_list,
        filter_kat=kat,
        kategori=KATEGORI, kategori_map=KATEGORI_MAP)


@pengeluaran_bp.route('/tambah', methods=['GET', 'POST'])
@login_required
def tambah():
    _init_table()
    if request.method == 'POST':
        data = {
            'tanggal':    request.form.get('tanggal', date.today().isoformat()),
            'kategori':   request.form.get('kategori', 'lainnya'),
            'keterangan': request.form.get('keterangan', '').strip(),
            'jumlah':     float(request.form.get('jumlah', 0) or 0),
            'dibayar_ke': request.form.get('dibayar_ke', '').strip(),
            'catatan':    request.form.get('catatan', '').strip(),
        }
        if not data['keterangan']:
            flash('Keterangan wajib diisi.', 'danger')
        elif data['jumlah'] <= 0:
            flash('Jumlah harus lebih dari 0.', 'danger')
        else:
            conn = get_db()
            conn.execute("""
                INSERT INTO pengeluaran
                    (tanggal, kategori, keterangan, jumlah, dibayar_ke, catatan)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data['tanggal'], data['kategori'], data['keterangan'],
                  data['jumlah'], data['dibayar_ke'], data['catatan']))
            conn.commit()
            conn.close()
            flash('Pengeluaran berhasil dicatat.', 'success')
            return redirect(url_for('pengeluaran.index'))

    return render_template('pengeluaran/form.html',
        mode='tambah', data={}, kategori=KATEGORI,
        today=date.today().isoformat())


@pengeluaran_bp.route('/edit/<int:eid>', methods=['GET', 'POST'])
@login_required
def edit(eid):
    _init_table()
    conn = get_db()
    row  = conn.execute("SELECT * FROM pengeluaran WHERE id=?", (eid,)).fetchone()
    conn.close()
    if not row:
        flash('Data tidak ditemukan.', 'danger')
        return redirect(url_for('pengeluaran.index'))

    if request.method == 'POST':
        data = {
            'tanggal':    request.form.get('tanggal', row['tanggal']),
            'kategori':   request.form.get('kategori', row['kategori']),
            'keterangan': request.form.get('keterangan', '').strip(),
            'jumlah':     float(request.form.get('jumlah', 0) or 0),
            'dibayar_ke': request.form.get('dibayar_ke', '').strip(),
            'catatan':    request.form.get('catatan', '').strip(),
        }
        if not data['keterangan']:
            flash('Keterangan wajib diisi.', 'danger')
        elif data['jumlah'] <= 0:
            flash('Jumlah harus lebih dari 0.', 'danger')
        else:
            conn = get_db()
            conn.execute("""
                UPDATE pengeluaran
                SET tanggal=?, kategori=?, keterangan=?, jumlah=?,
                    dibayar_ke=?, catatan=?
                WHERE id=?
            """, (data['tanggal'], data['kategori'], data['keterangan'],
                  data['jumlah'], data['dibayar_ke'], data['catatan'], eid))
            conn.commit()
            conn.close()
            flash('Pengeluaran berhasil diperbarui.', 'success')
            return redirect(url_for('pengeluaran.index'))

    return render_template('pengeluaran/form.html',
        mode='edit', data=dict(row), kategori=KATEGORI,
        today=date.today().isoformat())


@pengeluaran_bp.route('/hapus/<int:eid>')
@login_required
def hapus(eid):
    _init_table()
    conn = get_db()
    conn.execute("DELETE FROM pengeluaran WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    flash('Pengeluaran dihapus.', 'info')
    return redirect(url_for('pengeluaran.index'))
