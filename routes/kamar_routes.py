"""
routes/kamar_routes.py
Halaman Statistik Kamar — grid kartu semua kamar + detail per penghuni.
"""
from flask import Blueprint, render_template, abort
from utils.auth import login_required
from models.database import get_db
from datetime import date

kamar_bp = Blueprint('kamar', __name__, url_prefix='/kamar')


def _hitung_lama_tinggal(tanggal_masuk_str):
    """Kembalikan string lama tinggal dari tanggal_masuk (YYYY-MM-DD)."""
    if not tanggal_masuk_str:
        return '-'
    try:
        masuk = date.fromisoformat(tanggal_masuk_str)
        delta = date.today() - masuk
        hari  = delta.days
        if hari < 0:
            return 'Belum masuk'
        if hari < 30:
            return f'{hari} hari'
        bulan = hari // 30
        sisa  = hari % 30
        if bulan < 12:
            return f'{bulan} bln {sisa} hr' if sisa else f'{bulan} bulan'
        tahun  = bulan // 12
        s_bln  = bulan % 12
        return f'{tahun} thn {s_bln} bln' if s_bln else f'{tahun} tahun'
    except Exception:
        return '-'


# Daftar master nomor kamar sesuai Excel detailkamar.xlsx
SEMUA_KAMAR = [
    '101', '102', '103', '104', '105', '106',
    'M101', 'M102', 'M103', 'M104', 'M105',
    '201', '202', '203', '204', '205', '206',
    'M201', 'M202', 'M203', 'M204', 'M205',
    '301', '302', '303', '304', '305', '306',
    '401', '402', '403', '404-405', '406',
]
HARGA_SEWA_DEFAULT = 1800000


def _parse_cuci_ac(conn, semua_kamar):
    """
    Kembalikan dict {nomor_kamar: [list record cuci_ac]} dari tabel pengeluaran.
    Nomor kamar diparse dari kolom keterangan + catatan secara greedy —
    cocokkan token dari SEMUA_KAMAR yang muncul dalam teks.
    """
    rows = conn.execute("""
        SELECT id, tanggal, keterangan, catatan, jumlah, dibayar_ke
        FROM pengeluaran
        WHERE kategori = 'cuci_ac'
        ORDER BY tanggal DESC
    """).fetchall()

    # Urutkan dari terpanjang dulu agar 'M102' tidak salah match '102'
    kamar_sorted = sorted(semua_kamar, key=len, reverse=True)

    result = {k: [] for k in semua_kamar}

    for r in rows:
        gabung = f"{r['keterangan'] or ''} {r['catatan'] or ''}".upper()
        ditemukan = []
        for nomor in kamar_sorted:
            if nomor.upper() in gabung:
                ditemukan.append(nomor)

        if not ditemukan:
            # Tidak ada nomor kamar spesifik — skip
            continue

        rec = {
            'id':          r['id'],
            'tanggal':     r['tanggal'],
            'keterangan':  r['keterangan'],
            'catatan':     r['catatan'],
            'jumlah':      r['jumlah'],
            'teknisi':     r['dibayar_ke'],
        }
        for nomor in ditemukan:
            result[nomor].append(rec)

    return result


def _enrich_cuci_list(cuci_list):
    """Tambah field _hari_sejak, _label_sejak, _selang ke tiap record."""
    today = date.today()
    for i, c in enumerate(cuci_list):
        # Hari sejak cuci ini
        try:
            tgl = date.fromisoformat(c['tanggal'])
            hari = (today - tgl).days
            c['_hari_sejak'] = hari
            if hari == 0:
                c['_label_sejak'] = "Hari ini"
            elif hari < 30:
                c['_label_sejak'] = f"{hari} hari lalu"
            else:
                c['_label_sejak'] = f"{hari // 30} bulan lalu"
        except Exception:
            c['_hari_sejak'] = None
            c['_label_sejak'] = '—'

        # Selang ke record sebelumnya (index lebih besar = lebih lama)
        if i < len(cuci_list) - 1:
            try:
                tgl1 = date.fromisoformat(c['tanggal'])
                tgl2 = date.fromisoformat(cuci_list[i + 1]['tanggal'])
                hari_selang = (tgl1 - tgl2).days
                bln = hari_selang // 30
                sisa = hari_selang % 30
                if bln > 0:
                    c['_selang'] = f"{bln} bln {sisa} hr" if sisa else f"{bln} bulan"
                else:
                    c['_selang'] = f"{hari_selang} hari"
            except Exception:
                c['_selang'] = '—'
        else:
            c['_selang'] = '—'
    return cuci_list


@kamar_bp.route('/')
@login_required
def index():
    """Grid semua kamar (isi + kosong)."""
    conn = get_db()
    bulan_ini = date.today().strftime('%Y-%m')
    today     = date.today()

    # 1. Penghuni aktif + tagihan bulan ini
    rows = conn.execute("""
        SELECT
            p.id, p.nama, p.nomor_kamar, p.no_hp,
            p.tanggal_masuk, p.harga_sewa,
            t.status        AS status_bayar,
            t.jumlah        AS jumlah_tagihan,
            COALESCE(SUM(pb.jumlah_bayar), 0) AS total_bayar,
            (SELECT COUNT(*) FROM komplain k
             WHERE k.nomor_kamar = p.nomor_kamar
               AND k.status NOT IN ('selesai','ditutup')) AS komplain_aktif,
            (SELECT COUNT(*) FROM tagihan tx
             WHERE tx.penghuni_id = p.id
               AND tx.status = 'belum') AS tagihan_belum
        FROM penghuni p
        LEFT JOIN tagihan t
               ON t.penghuni_id = p.id AND t.bulan = ?
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE p.aktif = 1
        GROUP BY p.id
    """, (bulan_ini,)).fetchall()

    penghuni_map = {r['nomor_kamar']: dict(r) for r in rows}

    # 2. Tanggal keluar terakhir per kamar (dari checkout & penghuni nonaktif)
    checkout_map = {}
    for row in conn.execute("""
        SELECT nomor_kamar, MAX(tanggal_keluar) AS tgl
        FROM checkout GROUP BY nomor_kamar
    """).fetchall():
        checkout_map[row['nomor_kamar']] = row['tgl']

    for row in conn.execute("""
        SELECT nomor_kamar, MAX(tanggal_keluar) AS tgl
        FROM penghuni WHERE aktif=0 AND tanggal_keluar IS NOT NULL
        GROUP BY nomor_kamar
    """).fetchall():
        if row['nomor_kamar'] not in checkout_map:
            checkout_map[row['nomor_kamar']] = row['tgl']

    # 3. Data cuci AC dari pengeluaran
    cuci_ac_map = _parse_cuci_ac(conn, SEMUA_KAMAR)

    conn.close()

    # 4. Bangun kamar_list dari master list
    kamar_list = []
    for nomor in SEMUA_KAMAR:
        cuci_list = cuci_ac_map.get(nomor, [])
        # Hitung hari sejak cuci terakhir
        hari_sejak_cuci  = None
        label_cuci       = None
        if cuci_list:
            try:
                tgl = date.fromisoformat(cuci_list[0]['tanggal'])
                hari_sejak_cuci = (today - tgl).days
                if hari_sejak_cuci == 0:
                    label_cuci = "Hari ini"
                elif hari_sejak_cuci < 30:
                    label_cuci = f"{hari_sejak_cuci} hr lalu"
                else:
                    label_cuci = f"{hari_sejak_cuci // 30} bln lalu"
            except Exception:
                pass
        if nomor in penghuni_map:
            p = penghuni_map[nomor]
            p['lama_tinggal'] = _hitung_lama_tinggal(p['tanggal_masuk'])
            p['sisa_bayar']   = (p['jumlah_tagihan'] or 0) - p['total_bayar']
            p['status_kamar'] = 'isi'
            p['hari_kosong']  = None
            p['terakhir_diisi'] = None
            p['tipe_kamar']   = 'Standard AC'
            p['luas']         = 3.5
            p['kapasitas']    = 1
            p['cuci_ac_list']        = cuci_list
            p['hari_sejak_cuci']     = hari_sejak_cuci
            p['label_cuci']          = label_cuci
            kamar_list.append(p)
        else:
            # Hitung durasi kosong
            hari_kosong = None
            terakhir_diisi = None
            tgl_str = checkout_map.get(nomor)
            if tgl_str:
                try:
                    tgl = date.fromisoformat(tgl_str[:10])
                    hari_kosong    = (today - tgl).days
                    terakhir_diisi = tgl.strftime('%b %Y')
                except Exception:
                    pass

            kamar_list.append({
                'id':             None,
                'nomor_kamar':    nomor,
                'status_kamar':   'kosong',
                'nama':           None,
                'no_hp':          None,
                'harga_sewa':     HARGA_SEWA_DEFAULT,
                'tanggal_masuk':  None,
                'lama_tinggal':   None,
                'status_bayar':   None,
                'jumlah_tagihan': 0,
                'total_bayar':    0,
                'sisa_bayar':     0,
                'tagihan_belum':  0,
                'komplain_aktif': 0,
                'hari_kosong':    hari_kosong,
                'terakhir_diisi': terakhir_diisi,
                'tipe_kamar':     'Standard AC',
                'luas':           3.5,
                'kapasitas':      1,
                'cuci_ac_list':       cuci_list,
                'hari_sejak_cuci':    hari_sejak_cuci,
                'label_cuci':         label_cuci,
            })

    return render_template('kamar/index.html',
                           kamar_list=kamar_list,
                           bulan_ini=bulan_ini)


@kamar_bp.route('/kosong/<nomor_kamar>')
@login_required
def detail_kosong(nomor_kamar):
    """Halaman detail kamar kosong."""
    conn = get_db()
    today = date.today()

    # Riwayat penghuni yang pernah di kamar ini (sudah tidak aktif / ada tanggal keluar)
    riwayat_rows = conn.execute("""
        SELECT nama, no_hp, tanggal_masuk, tanggal_keluar, harga_sewa
        FROM penghuni
        WHERE nomor_kamar = ? AND (aktif = 0 OR tanggal_keluar IS NOT NULL)
        ORDER BY tanggal_keluar DESC
    """, (nomor_kamar,)).fetchall()

    # Juga cek tabel checkout
    checkout_rows = conn.execute("""
        SELECT nama, tanggal_masuk, tanggal_keluar, lama_tinggal_hari, harga_sewa
        FROM checkout
        WHERE nomor_kamar = ?
        ORDER BY tanggal_keluar DESC
    """, (nomor_kamar,)).fetchall()

    # Komplain untuk kamar ini
    komplain_list = conn.execute("""
        SELECT * FROM komplain
        WHERE nomor_kamar = ?
        ORDER BY created_at DESC
    """, (nomor_kamar,)).fetchall()
    komplain_list = [dict(r) for r in komplain_list]

    # Semua pembayaran dari penghuni yang pernah di kamar ini
    pembayaran_list = conn.execute("""
        SELECT pb.*, t.bulan, p.nama AS nama_penghuni
        FROM pembayaran pb
        JOIN tagihan t ON t.id = pb.tagihan_id
        JOIN penghuni p ON p.id = pb.penghuni_id
        WHERE p.nomor_kamar = ?
        ORDER BY pb.tanggal_bayar DESC
    """, (nomor_kamar,)).fetchall()
    pembayaran_list = [dict(r) for r in pembayaran_list]

    conn.close()

    # Gabung & dedup berdasarkan tanggal_keluar
    riwayat_penghuni = []
    seen = set()
    for r in list(checkout_rows) + list(riwayat_rows):
        r = dict(r)
        key = (r.get('nama'), r.get('tanggal_keluar'))
        if key in seen:
            continue
        seen.add(key)
        # Hitung lama tinggal kalau belum ada
        if not r.get('lama_tinggal_hari') and r.get('tanggal_masuk') and r.get('tanggal_keluar'):
            try:
                tgl_m = date.fromisoformat(r['tanggal_masuk'][:10])
                tgl_k = date.fromisoformat(r['tanggal_keluar'][:10])
                r['lama_tinggal_hari'] = (tgl_k - tgl_m).days
            except Exception:
                r['lama_tinggal_hari'] = None
        hari = r.get('lama_tinggal_hari') or 0
        bulan = hari // 30
        r['lama_tinggal'] = f"{bulan} bulan" if bulan else f"{hari} hari"
        # Format tanggal
        for field in ('tanggal_masuk', 'tanggal_keluar'):
            if r.get(field):
                try:
                    r[field] = date.fromisoformat(r[field][:10]).strftime('%d %b %Y')
                except Exception:
                    pass
        riwayat_penghuni.append(r)

    # Hitung hari kosong dari tanggal keluar terakhir
    hari_kosong = None
    tanggal_kosong = None
    terakhir_diisi = None
    if riwayat_penghuni:
        tgl_str = checkout_rows[0]['tanggal_keluar'] if checkout_rows else riwayat_rows[0]['tanggal_keluar'] if riwayat_rows else None
        if tgl_str:
            try:
                tgl = date.fromisoformat(tgl_str[:10])
                hari_kosong    = (today - tgl).days
                tanggal_kosong = tgl.strftime('%d %b %Y')
                terakhir_diisi = tgl.strftime('%b %Y')
            except Exception:
                pass

    # Buat objek kamar dari konstanta
    kamar = {
        'nomor_kamar':   nomor_kamar,
        'tipe_kamar':    'Standard AC',
        'lantai':        nomor_kamar[0] if nomor_kamar[0].isdigit() else nomor_kamar[:2],
        'luas':          3.5,
        'kapasitas':     1,
        'harga_sewa':    HARGA_SEWA_DEFAULT,
        'fasilitas':     None,
        'deskripsi':     None,
        'hari_kosong':   hari_kosong,
        'tanggal_kosong': tanggal_kosong,
        'terakhir_diisi': terakhir_diisi,
    }

    # Cuci AC dari pengeluaran
    cuci_ac_map  = _parse_cuci_ac(conn, SEMUA_KAMAR)
    cuci_ac_list = _enrich_cuci_list(cuci_ac_map.get(nomor_kamar, []))

    return render_template('kamar/detail_kosong.html',
                           kamar            = kamar,
                           riwayat_penghuni = riwayat_penghuni,
                           komplain_list    = komplain_list,
                           pembayaran_list  = pembayaran_list,
                           cuci_ac_list     = cuci_ac_list)


@kamar_bp.route('/<int:penghuni_id>')
@login_required
def detail(penghuni_id):
    """Halaman detail lengkap satu penghuni."""
    conn = get_db()

    penghuni = conn.execute(
        "SELECT * FROM penghuni WHERE id = ? AND aktif = 1", (penghuni_id,)
    ).fetchone()
    if not penghuni:
        abort(404)

    penghuni = dict(penghuni)
    penghuni['lama_tinggal'] = _hitung_lama_tinggal(penghuni['tanggal_masuk'])

    # Semua tagihan + total bayar per tagihan
    tagihan_rows = conn.execute("""
        SELECT
            t.*,
            COALESCE(SUM(pb.jumlah_bayar), 0) AS total_bayar
        FROM tagihan t
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE t.penghuni_id = ?
        GROUP BY t.id
        ORDER BY t.bulan DESC
    """, (penghuni_id,)).fetchall()
    tagihan_list = []
    for t in tagihan_rows:
        d = dict(t)
        d['sisa'] = d['jumlah'] - d['total_bayar']
        tagihan_list.append(d)

    # Semua pembayaran
    pembayaran_list = conn.execute("""
        SELECT pb.*, t.bulan
        FROM pembayaran pb
        JOIN tagihan t ON t.id = pb.tagihan_id
        WHERE pb.penghuni_id = ?
        ORDER BY pb.tanggal_bayar DESC
    """, (penghuni_id,)).fetchall()

    # Notifikasi WA
    notif_list = conn.execute("""
        SELECT * FROM notif_wa
        WHERE penghuni_id = ?
        ORDER BY tanggal_kirim DESC
        LIMIT 20
    """, (penghuni_id,)).fetchall()

    # Komplain kamar ini
    komplain_list = conn.execute("""
        SELECT * FROM komplain
        WHERE nomor_kamar = ?
        ORDER BY created_at DESC
    """, (penghuni['nomor_kamar'],)).fetchall()

    # Riwayat checkin/checkout kamar ini (semua penghuni yang pernah di kamar ini)
    riwayat_kamar = []
    seen_ids = set()

    # Dari tabel checkout
    co_rows = conn.execute("""
        SELECT c.penghuni_id, c.nama, c.tanggal_masuk, c.tanggal_keluar,
               c.lama_tinggal_hari, c.harga_sewa, c.deposit_awal,
               c.deposit_dikembalikan, c.tagihan_belum_lunas,
               c.kondisi_kamar, c.catatan, c.created_at AS checkout_at,
               p.no_hp
        FROM checkout c
        LEFT JOIN penghuni p ON p.id = c.penghuni_id
        WHERE c.nomor_kamar = ?
        ORDER BY c.tanggal_keluar DESC
    """, (penghuni['nomor_kamar'],)).fetchall()
    for r in co_rows:
        d = dict(r)
        d['sumber'] = 'checkout'
        seen_ids.add(d['penghuni_id'])
        riwayat_kamar.append(d)

    # Dari tabel penghuni nonaktif yang belum ada di checkout
    ph_rows = conn.execute("""
        SELECT id AS penghuni_id, nama, tanggal_masuk, tanggal_keluar,
               NULL AS lama_tinggal_hari, harga_sewa, deposit AS deposit_awal,
               NULL AS deposit_dikembalikan, NULL AS tagihan_belum_lunas,
               NULL AS kondisi_kamar, NULL AS catatan, NULL AS checkout_at,
               no_hp
        FROM penghuni
        WHERE nomor_kamar = ? AND aktif = 0 AND id != ?
        ORDER BY tanggal_keluar DESC
    """, (penghuni['nomor_kamar'], penghuni_id)).fetchall()
    for r in ph_rows:
        d = dict(r)
        if d['penghuni_id'] not in seen_ids:
            # Hitung lama tinggal
            if d['tanggal_masuk'] and d['tanggal_keluar']:
                try:
                    from datetime import date as _date
                    m = _date.fromisoformat(d['tanggal_masuk'][:10])
                    k = _date.fromisoformat(d['tanggal_keluar'][:10])
                    d['lama_tinggal_hari'] = (k - m).days
                except Exception:
                    pass
            d['sumber'] = 'penghuni'
            riwayat_kamar.append(d)

    # Ringkasan statistik
    total_tagihan   = sum(t['jumlah']      for t in tagihan_list)
    total_terbayar  = sum(t['total_bayar'] for t in tagihan_list)
    jumlah_lunas    = sum(1 for t in tagihan_list if t['status'] == 'lunas')
    jumlah_belum    = sum(1 for t in tagihan_list if t['status'] != 'lunas')

    # Cuci AC dari pengeluaran
    cuci_ac_map  = _parse_cuci_ac(conn, SEMUA_KAMAR)
    cuci_ac_list = _enrich_cuci_list(cuci_ac_map.get(penghuni['nomor_kamar'], []))

    conn.close()
    return render_template('kamar/detail.html',
                           penghuni        = penghuni,
                           tagihan_list    = tagihan_list,
                           pembayaran_list = [dict(r) for r in pembayaran_list],
                           notif_list      = [dict(r) for r in notif_list],
                           komplain_list   = [dict(r) for r in komplain_list],
                           riwayat_kamar   = riwayat_kamar,
                           total_tagihan   = total_tagihan,
                           total_terbayar  = total_terbayar,
                           jumlah_lunas    = jumlah_lunas,
                           jumlah_belum    = jumlah_belum,
                           cuci_ac_list    = cuci_ac_list)
