"""
Ganti/update fungsi route kamar.index di blueprint kamar.
Tambahkan daftar SEMUA_KAMAR sesuai nomor di Excel,
lalu merge dengan data penghuni aktif dari DB.
"""

from datetime import date, datetime

# ── Daftar master nomor kamar (sesuai Excel detailkamar.xlsx) ──
SEMUA_KAMAR = [
    '101', '102', '103', '104', '105', '106',
    'M101', 'M102', 'M103', 'M104', 'M105',
    '201', '202', '203', '204', '205', '206',
    'M201', 'M202', 'M203', 'M204', 'M205',
    '301', '302', '303', '304', '305', '306',
    '401', '402', '403', '404-405', '406',
]

HARGA_SEWA_DEFAULT = 1800000


def get_kamar_list(db):
    """
    Kembalikan list dict untuk semua 33 kamar:
    - kamar isi  → data dari tabel penghuni + tagihan bulan ini
    - kamar kosong → status_kamar='kosong', hari_kosong, terakhir_diisi dari checkout
    """
    today = date.today()
    bulan_ini = today.strftime('%Y-%m')

    # ── 1. Penghuni aktif ──────────────────────────────────────────
    penghuni_aktif = db.execute("""
        SELECT p.id, p.nama, p.nomor_kamar, p.no_hp, p.tanggal_masuk, p.harga_sewa,
               t.jumlah        AS jumlah_tagihan,
               t.total_bayar   AS total_bayar,
               (t.jumlah - COALESCE(t.total_bayar, 0)) AS sisa_bayar,
               t.status        AS status_bayar
        FROM penghuni p
        LEFT JOIN tagihan t
            ON t.penghuni_id = p.id AND t.bulan = :bulan
        WHERE p.aktif = 1
    """, {'bulan': bulan_ini}).fetchall()

    penghuni_map = {row['nomor_kamar']: row for row in penghuni_aktif}

    # ── 2. Tagihan belum lunas (tunggakan) per penghuni ───────────
    tunggakan = db.execute("""
        SELECT penghuni_id, COUNT(*) AS jml
        FROM tagihan
        WHERE status IN ('belum', 'sebagian')
        GROUP BY penghuni_id
    """).fetchall()
    tunggakan_map = {row['penghuni_id']: row['jml'] for row in tunggakan}

    # ── 3. Komplain aktif per penghuni ───────────────────────────
    komplain = db.execute("""
        SELECT penghuni_id, COUNT(*) AS jml
        FROM komplain
        WHERE status NOT IN ('selesai')
        GROUP BY penghuni_id
    """).fetchall()
    komplain_map = {row['penghuni_id']: row['jml'] for row in komplain}

    # ── 4. Riwayat checkout per nomor kamar (untuk hari_kosong) ──
    checkout_rows = db.execute("""
        SELECT nomor_kamar, MAX(tanggal_keluar) AS terakhir_keluar
        FROM checkout
        GROUP BY nomor_kamar
    """).fetchall()
    checkout_map = {row['nomor_kamar']: row['terakhir_keluar'] for row in checkout_rows}

    # Fallback: penghuni non-aktif dengan tanggal_keluar
    nonaktif_rows = db.execute("""
        SELECT nomor_kamar, MAX(tanggal_keluar) AS terakhir_keluar
        FROM penghuni
        WHERE aktif = 0 AND tanggal_keluar IS NOT NULL
        GROUP BY nomor_kamar
    """).fetchall()
    for row in nonaktif_rows:
        if row['nomor_kamar'] not in checkout_map:
            checkout_map[row['nomor_kamar']] = row['terakhir_keluar']

    # ── 5. Bangun kamar_list ──────────────────────────────────────
    kamar_list = []

    for nomor in SEMUA_KAMAR:
        if nomor in penghuni_map:
            # ── Kamar ISI ──
            p = penghuni_map[nomor]

            # Lama tinggal
            try:
                tgl_masuk = datetime.strptime(p['tanggal_masuk'], '%Y-%m-%d').date()
                hari = (today - tgl_masuk).days
                bulan_tinggal = hari // 30
                lama_tinggal = f"{bulan_tinggal} bln" if bulan_tinggal else f"{hari} hari"
            except Exception:
                lama_tinggal = '—'

            # Status bayar
            status_bayar = p['status_bayar'] or 'notagihan'
            jumlah = p['jumlah_tagihan'] or 0
            sisa   = p['sisa_bayar'] or 0

            kamar_list.append({
                'id':            p['id'],
                'nomor_kamar':   nomor,
                'status_kamar':  'isi',
                'nama':          p['nama'],
                'no_hp':         p['no_hp'],
                'harga_sewa':    p['harga_sewa'] or HARGA_SEWA_DEFAULT,
                'tanggal_masuk': p['tanggal_masuk'],
                'lama_tinggal':  lama_tinggal,
                'status_bayar':  status_bayar,
                'jumlah_tagihan': jumlah,
                'sisa_bayar':    sisa,
                'tagihan_belum': tunggakan_map.get(p['id'], 0),
                'komplain_aktif': komplain_map.get(p['id'], 0),
                # kosong fields — tidak relevan
                'hari_kosong':    None,
                'tanggal_kosong': None,
                'terakhir_diisi': None,
                'tipe_kamar':    'Standard AC',
                'luas':          3.5,
                'kapasitas':     1,
            })

        else:
            # ── Kamar KOSONG ──
            tgl_keluar_str = checkout_map.get(nomor)
            hari_kosong    = None
            tanggal_kosong = None
            terakhir_diisi = None

            if tgl_keluar_str:
                try:
                    tgl_keluar = datetime.strptime(tgl_keluar_str[:10], '%Y-%m-%d').date()
                    hari_kosong    = (today - tgl_keluar).days
                    tanggal_kosong = tgl_keluar.strftime('%d %b %Y')
                    terakhir_diisi = tgl_keluar.strftime('%b %Y')
                except Exception:
                    pass

            kamar_list.append({
                'id':            None,        # tidak ada penghuni
                'nomor_kamar':   nomor,
                'status_kamar':  'kosong',
                'nama':          None,
                'no_hp':         None,
                'harga_sewa':    HARGA_SEWA_DEFAULT,
                'tanggal_masuk': None,
                'lama_tinggal':  None,
                'status_bayar':  None,
                'jumlah_tagihan': 0,
                'sisa_bayar':    0,
                'tagihan_belum': 0,
                'komplain_aktif': 0,
                # kosong fields
                'hari_kosong':    hari_kosong,
                'tanggal_kosong': tanggal_kosong,
                'terakhir_diisi': terakhir_diisi,
                'tipe_kamar':    'Standard AC',
                'luas':          3.5,
                'kapasitas':     1,
            })

    return kamar_list


# ── Route ──────────────────────────────────────────────────────────
@kamar_bp.route('/kamar')
@login_required
def index():
    bulan_ini = date.today().strftime('%Y-%m')
    kamar_list = get_kamar_list(db)
    return render_template('kamar/index.html',
        kamar_list=kamar_list,
        bulan_ini=bulan_ini,
    )
