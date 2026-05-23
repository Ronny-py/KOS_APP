import os
"""
routes/laporan_routes.py
Laporan pembayaran & pengeluaran — termasuk export CSV dan PDF.

Dependency tambahan:
    pip install reportlab
"""
import io
import csv
import datetime

from flask import Blueprint, render_template, request, send_file
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus import Image as RLImage
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from models.database import get_db
from utils.auth import login_required

laporan_bp = Blueprint('laporan', __name__, url_prefix='/laporan')

BIRU_TUA = colors.HexColor('#1e3a5f')
BIRU_MUD = colors.HexColor('#2980b9')
HIJAU    = colors.HexColor('#27ae60')
MERAH    = colors.HexColor('#e74c3c')
KUNING   = colors.HexColor('#f39c12')
ABU      = colors.HexColor('#ecf0f1')
ABU_TUA  = colors.HexColor('#bdc3c7')

NAMA_BULAN = [
    '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
]

def fmt_rupiah(nilai):
    try:
        return "Rp {:,}".format(int(nilai)).replace(',', '.')
    except Exception:
        return "Rp 0"

def _get_filter_params():
    now = datetime.date.today()
    bulan = request.args.get('bulan', type=int, default=now.month)
    tahun = request.args.get('tahun', type=int, default=now.year)
    return bulan, tahun

def _tahun_list(db):
    rows = db.execute("SELECT DISTINCT substr(bulan,1,4) AS tahun FROM tagihan ORDER BY tahun DESC").fetchall()
    return [int(r['tahun']) for r in rows] or [datetime.date.today().year]

def _tahun_list_pengeluaran(db):
    rows = db.execute(
        "SELECT DISTINCT strftime('%Y', tanggal) AS tahun FROM pengeluaran ORDER BY tahun DESC"
    ).fetchall()
    return [int(r['tahun']) for r in rows] or [datetime.date.today().year]

def _base_style():
    return TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ABU]),
        ('GRID',          (0, 0), (-1, -1), 0.4, ABU_TUA),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ])

def _header_cmds():
    return [
        ('BACKGROUND', (0, 0), (-1, 0), BIRU_TUA),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, 0), 8),
        ('ALIGN',      (0, 0), (-1, 0), 'CENTER'),
    ]

def _footer_cmds(last_row):
    return [
        ('BACKGROUND', (0, last_row), (-1, last_row), BIRU_TUA),
        ('TEXTCOLOR',  (0, last_row), (-1, last_row), colors.white),
        ('FONTNAME',   (0, last_row), (-1, last_row), 'Helvetica-Bold'),
    ]

def _build_header_paragraph(title, subtitle, styles):
    s_title = ParagraphStyle('judul', parent=styles['Title'],
                             fontSize=16, textColor=BIRU_TUA,
                             spaceAfter=2, alignment=TA_CENTER)
    s_sub   = ParagraphStyle('sub', parent=styles['Normal'],
                             fontSize=9, textColor=colors.grey,
                             alignment=TA_CENTER)
    tgl = datetime.date.today().strftime('%d %B %Y')
    return [
        Paragraph(title, s_title),
        Paragraph(subtitle, s_sub),
        Paragraph(f'Dicetak pada: {tgl}', s_sub),
        Spacer(1, 0.4 * cm),
        HRFlowable(width='100%', thickness=1.5, color=BIRU_TUA),
        Spacer(1, 0.3 * cm),
    ]


# ── Helper query pengeluaran ───────────────────────────────────────────────
def _query_pengeluaran(db, bulan, tahun, kategori=None):
    q = """
        SELECT tanggal, kategori, keterangan, jumlah
        FROM pengeluaran
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """
    p = [f"{bulan:02d}", str(tahun)]
    if kategori:
        q += " AND kategori = ?"
        p.append(kategori)
    q += " ORDER BY tanggal DESC"
    return db.execute(q, p).fetchall()

def _query_kategori_summary(db, bulan, tahun):
    return db.execute("""
        SELECT COALESCE(kategori, 'Lainnya') AS kategori, SUM(jumlah) AS total
        FROM pengeluaran
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
        GROUP BY kategori
        ORDER BY total DESC
    """, (f"{bulan:02d}", str(tahun))).fetchall()

def _query_pemasukan(db, bulan, tahun):
    row = db.execute("""
        SELECT COALESCE(SUM(jumlah_bayar), 0) AS total
        FROM pembayaran
        WHERE strftime('%m', tanggal_bayar) = ? AND strftime('%Y', tanggal_bayar) = ?
    """, (f"{bulan:02d}", str(tahun))).fetchone()
    return row['total'] if row else 0


# ── 1. Laporan Pembayaran HTML ─────────────────────────────────────────────
@laporan_bp.route('/pembayaran')
@login_required
def pembayaran():
    bulan, tahun = _get_filter_params()
    db = get_db()
    rows = db.execute("""
        SELECT p.nama AS nama_penghuni, p.nomor_kamar,
               CAST(substr(t.bulan,6,2) AS INTEGER) AS bulan,
               CAST(substr(t.bulan,1,4) AS INTEGER) AS tahun,
               t.jumlah AS jumlah_tagihan,
               COALESCE(SUM(py.jumlah_bayar), 0) AS total_bayar, t.status
        FROM tagihan t
        JOIN penghuni p ON p.id = t.penghuni_id
        LEFT JOIN pembayaran py ON py.tagihan_id = t.id
        WHERE substr(t.bulan,6,2) = printf('%02d', ?) AND substr(t.bulan,1,4) = ?
        GROUP BY t.id ORDER BY p.nomor_kamar, p.nama
    """, (bulan, str(tahun))).fetchall()

    total_tagihan  = sum(r['jumlah_tagihan'] for r in rows)
    total_terbayar = sum(r['total_bayar']    for r in rows)
    total_sisa     = total_tagihan - total_terbayar
    jumlah_lunas   = sum(1 for r in rows if r['status'] == 'lunas')
    jumlah_belum   = len(rows) - jumlah_lunas

    return render_template('laporan/pembayaran.html',
        rows=rows, bulan=bulan, tahun=tahun,
        total_tagihan=total_tagihan, total_terbayar=total_terbayar,
        total_sisa=total_sisa, jumlah_lunas=jumlah_lunas,
        jumlah_belum=jumlah_belum, tahun_list=_tahun_list(db))


# ── 2. Export Pembayaran CSV ───────────────────────────────────────────────
@laporan_bp.route('/pembayaran/export/csv')
@login_required
def export_pembayaran_csv():
    bulan, tahun = _get_filter_params()
    db = get_db()
    rows = db.execute("""
        SELECT p.nama, p.nomor_kamar,
               CAST(substr(t.bulan,6,2) AS INTEGER) AS bulan,
               CAST(substr(t.bulan,1,4) AS INTEGER) AS tahun,
               t.jumlah AS jumlah_tagihan,
               COALESCE(SUM(py.jumlah_bayar), 0) AS total_bayar, t.status
        FROM tagihan t
        JOIN penghuni p ON p.id = t.penghuni_id
        LEFT JOIN pembayaran py ON py.tagihan_id = t.id
        WHERE substr(t.bulan,6,2) = printf('%02d', ?) AND substr(t.bulan,1,4) = ?
        GROUP BY t.id ORDER BY p.nomor_kamar
    """, (bulan, str(tahun))).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['No','Nama','Kamar','Bulan','Tahun',
                     'Tagihan (Rp)','Terbayar (Rp)','Sisa (Rp)','Status'])
    for i, r in enumerate(rows, 1):
        sisa = r['jumlah_tagihan'] - r['total_bayar']
        writer.writerow([i, r['nama'], r['nomor_kamar'],
                         NAMA_BULAN[r['bulan']], r['tahun'],
                         r['jumlah_tagihan'], r['total_bayar'], sisa, r['status']])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv', as_attachment=True,
                     download_name=f"laporan_pembayaran_{bulan:02d}_{tahun}.csv")


# ── 3. Export Pembayaran PDF ───────────────────────────────────────────────
def _load_bukti_images(db, bulan, tahun):
    """
    Ambil semua bukti transfer untuk pembayaran pada bulan & tahun ini.
    Return: list of dict {kamar, nama, tanggal_bayar, filepath, original_name}
    Hanya file gambar (bukan PDF) yang bisa dirender inline di PDF.
    """
    rows = db.execute("""
        SELECT p.nomor_kamar, p.nama,
               py.tanggal_bayar,
               pb.filename, pb.original_name
        FROM pembayaran py
        JOIN tagihan  t  ON py.tagihan_id  = t.id
        JOIN penghuni p  ON py.penghuni_id = p.id
        LEFT JOIN pembayaran_bukti pb ON pb.pembayaran_id = py.id
        WHERE substr(t.bulan,6,2) = printf('%02d', ?)
          AND substr(t.bulan,1,4) = ?
          AND pb.filename IS NOT NULL
        ORDER BY p.nomor_kamar, py.tanggal_bayar, pb.id
    """, (bulan, str(tahun))).fetchall()

    # Juga cek kolom bukti_file lama (backward compat, satu file per pembayaran)
    rows_legacy = db.execute("""
        SELECT p.nomor_kamar, p.nama,
               py.tanggal_bayar,
               py.bukti_file AS filename,
               py.bukti_file AS original_name
        FROM pembayaran py
        JOIN tagihan  t  ON py.tagihan_id  = t.id
        JOIN penghuni p  ON py.penghuni_id = p.id
        LEFT JOIN pembayaran_bukti pb ON pb.pembayaran_id = py.id
        WHERE substr(t.bulan,6,2) = printf('%02d', ?)
          AND substr(t.bulan,1,4) = ?
          AND py.bukti_file IS NOT NULL
          AND pb.id IS NULL
        ORDER BY p.nomor_kamar, py.tanggal_bayar
    """, (bulan, str(tahun))).fetchall()

    IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    result = []
    for r in list(rows) + list(rows_legacy):
        if not r['filename']:
            continue
        ext = ('.' + r['filename'].rsplit('.', 1)[-1]).lower() if '.' in r['filename'] else ''
        if ext not in IMAGE_EXT:
            continue  # skip PDF, hanya gambar yang bisa di-embed
        fpath = os.path.join('static', 'uploads', r['filename'])
        if not os.path.exists(fpath):
            continue
        result.append({
            'kamar':        r['nomor_kamar'],
            'nama':         r['nama'],
            'tanggal_bayar': str(r['tanggal_bayar'])[:16],
            'filepath':     fpath,
            'original_name': r['original_name'] or r['filename'],
        })
    return result


def _build_lampiran_bukti(bukti_list, styles, per_baris=2):
    """
    Buat halaman lampiran berisi grid gambar bukti transfer.
    per_baris: jumlah gambar per baris (2 atau maksimal 4 bergantung lebar).
    Ukuran setiap sel: sekitar 9 cm x 10 cm agar tetap terbaca.
    """
    import math

    if not bukti_list:
        return []

    s_judul = ParagraphStyle('lmp_judul', parent=styles['Normal'],
                             fontSize=14, textColor=BIRU_TUA,
                             fontName='Helvetica-Bold',
                             spaceAfter=4, alignment=TA_CENTER)
    s_sub   = ParagraphStyle('lmp_sub', parent=styles['Normal'],
                             fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    s_cap   = ParagraphStyle('lmp_cap', parent=styles['Normal'],
                             fontSize=7, textColor=colors.HexColor('#444444'),
                             alignment=TA_CENTER, leading=10)

    elems = [
        PageBreak(),
        Paragraph('LAMPIRAN — BUKTI TRANSFER', s_judul),
        Paragraph(f'Total {len(bukti_list)} gambar bukti', s_sub),
        Spacer(1, 0.3*cm),
        HRFlowable(width='100%', thickness=1, color=BIRU_TUA),
        Spacer(1, 0.4*cm),
    ]

    # Landscape A4 usable width ≈ 25.7 cm (29.7 - 2×2 cm margin)
    # Portrait A4 ≈ 18 cm usable
    # Kita pakai landscape agar per_baris=2 → tiap gambar ~12 cm lebar
    # per_baris=4 → ~6 cm (masih cukup terbaca untuk foto struk)
    USABLE_W   = 25.7 * cm          # landscape A4 usable width
    GAP        = 0.4 * cm
    IMG_W      = (USABLE_W - (per_baris - 1) * GAP) / per_baris
    IMG_H      = IMG_W * 1.3        # rasio portrait untuk struk transfer
    MAX_IMG_H  = 14 * cm            # batas tinggi agar tidak terlalu memanjang

    IMG_H = min(IMG_H, MAX_IMG_H)

    # Susun dalam tabel grid per_baris kolom
    col_w = [IMG_W] * per_baris
    rows_grid = []
    current_row_imgs  = []
    current_row_caps  = []

    for b in bukti_list:
        try:
            img = RLImage(b['filepath'], width=IMG_W, height=IMG_H)
            img.hAlign = 'CENTER'
        except Exception:
            continue  # skip jika gambar rusak

        caption_text = (
            f"<b>Kamar {b['kamar']} — {b['nama']}</b><br/>"
            f"{b['tanggal_bayar']}"
        )
        cap = Paragraph(caption_text, s_cap)

        current_row_imgs.append(img)
        current_row_caps.append(cap)

        if len(current_row_imgs) == per_baris:
            rows_grid.append(current_row_imgs)
            rows_grid.append(current_row_caps)
            current_row_imgs = []
            current_row_caps = []

    # Sisa yang belum genap per_baris
    if current_row_imgs:
        # Pad dengan string kosong
        while len(current_row_imgs) < per_baris:
            current_row_imgs.append('')
            current_row_caps.append('')
        rows_grid.append(current_row_imgs)
        rows_grid.append(current_row_caps)

    if not rows_grid:
        return elems

    # Buat row heights: baris gambar → IMG_H, baris caption → 0.7 cm
    n_pairs = len(rows_grid) // 2
    row_heights = []
    for _ in range(n_pairs):
        row_heights.append(IMG_H)
        row_heights.append(0.7 * cm)

    tbl = Table(rows_grid, colWidths=col_w, rowHeights=row_heights)
    tbl.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        # Grid tipis di sekitar setiap sel gambar (baris genap = gambar)
        ('BOX',           (0, 0), (-1, -1), 0.5, ABU_TUA),
        ('INNERGRID',     (0, 0), (-1, -1), 0.3, ABU_TUA),
    ]))
    elems.append(tbl)
    return elems


@laporan_bp.route('/pembayaran/export/pdf')
@login_required
def export_pembayaran_pdf():
    bulan, tahun = _get_filter_params()
    db = get_db()
    rows = db.execute("""
        SELECT p.nama, p.nomor_kamar,
               CAST(substr(t.bulan,6,2) AS INTEGER) AS bulan,
               CAST(substr(t.bulan,1,4) AS INTEGER) AS tahun,
               t.jumlah AS jumlah_tagihan,
               COALESCE(SUM(py.jumlah_bayar), 0) AS total_bayar, t.status
        FROM tagihan t
        JOIN penghuni p ON p.id = t.penghuni_id
        LEFT JOIN pembayaran py ON py.tagihan_id = t.id
        WHERE substr(t.bulan,6,2) = printf('%02d', ?) AND substr(t.bulan,1,4) = ?
        GROUP BY t.id ORDER BY p.nomor_kamar
    """, (bulan, str(tahun))).fetchall()

    total_tagihan  = sum(r['jumlah_tagihan'] for r in rows)
    total_terbayar = sum(r['total_bayar']    for r in rows)
    total_sisa     = total_tagihan - total_terbayar
    jumlah_lunas   = sum(1 for r in rows if r['status'] == 'lunas')
    jumlah_belum   = len(rows) - jumlah_lunas

    # Ambil bukti gambar untuk lampiran
    bukti_list = _load_bukti_images(db, bulan, tahun)
    db.close()

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=landscape(A4),
                               leftMargin=1.5*cm, rightMargin=1.5*cm,
                               topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    story  = _build_header_paragraph(
        'LAPORAN PEMBAYARAN KOST',
        f'Periode: {NAMA_BULAN[bulan]} {tahun}', styles)

    # Summary
    summary_data = [
        ['Total Tagihan','Sudah Lunas','Belum Lunas','Total Terbayar','Total Sisa'],
        [str(len(rows)), str(jumlah_lunas), str(jumlah_belum),
         fmt_rupiah(total_terbayar), fmt_rupiah(total_sisa)],
    ]
    t_sum = Table(summary_data, colWidths=[4*cm]*5)
    t_sum.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,0), BIRU_TUA),
        ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
        ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
        ('FONTNAME',      (0,1),(-1,1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0),(-1,-1), 10),
        ('ALIGN',         (0,0),(-1,-1), 'CENTER'),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0),(-1,-1), 6),
        ('BOTTOMPADDING', (0,0),(-1,-1), 6),
        ('GRID',          (0,0),(-1,-1), 0.5, colors.white),
        ('BACKGROUND',    (1,1),(1,1), colors.HexColor('#d5f5e3')),
        ('BACKGROUND',    (2,1),(2,1), colors.HexColor('#fde8d8')),
        ('BACKGROUND',    (5,1),(5,1), colors.HexColor('#fde8d8')),
        ('TEXTCOLOR',     (5,1),(5,1), MERAH),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 0.4*cm))

    # Tabel data
    header = ['No','Kamar','Nama Penghuni','Tagihan','Terbayar','Sisa','Status']
    data   = [header]
    for i, r in enumerate(rows, 1):
        sisa = r['jumlah_tagihan'] - r['total_bayar']
        data.append([str(i), r['nomor_kamar'], r['nama'],
                     fmt_rupiah(r['jumlah_tagihan']),
                     fmt_rupiah(r['total_bayar']),
                     fmt_rupiah(sisa),
                     r['status'].upper()])
    data.append(['','','TOTAL',
                 fmt_rupiah(total_tagihan), fmt_rupiah(total_terbayar),
                 fmt_rupiah(total_sisa), ''])

    col_w = [1*cm, 2*cm, 6*cm, 4*cm, 4*cm, 4*cm, 2.5*cm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    ts = _base_style()
    for cmd in _header_cmds(): ts.add(*cmd)
    for cmd in _footer_cmds(len(data)-1): ts.add(*cmd)
    for col in [3,4,5]:
        ts.add('ALIGN', (col,1),(col,-1), 'RIGHT')
    ts.add('ALIGN',(0,1),(0,-1),'CENTER')
    ts.add('ALIGN',(1,1),(1,-1),'CENTER')
    ts.add('ALIGN',(6,1),(6,-1),'CENTER')
    for i, r in enumerate(rows, 1):
        sisa = r['jumlah_tagihan'] - r['total_bayar']
        if sisa > 0:
            ts.add('TEXTCOLOR',(5,i),(5,i), MERAH)
        ts.add('TEXTCOLOR',(6,i),(6,i), HIJAU if r['status']=='lunas' else MERAH)
    t.setStyle(ts)
    story.append(t)

    # ── Lampiran bukti transfer (halaman terpisah di akhir) ──
    if bukti_list:
        # Tentukan jumlah per baris: 2 jika sedikit gambar, 4 jika banyak
        per_baris = 2 if len(bukti_list) <= 8 else 4
        story += _build_lampiran_bukti(bukti_list, styles, per_baris=per_baris)

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f"laporan_pembayaran_{bulan:02d}_{tahun}.pdf")


# ── 4. Laporan Pengeluaran HTML ────────────────────────────────────────────
@laporan_bp.route('/pengeluaran')
@login_required
def pengeluaran():
    bulan, tahun     = _get_filter_params()
    filter_kategori  = request.args.get('kategori', '')
    db               = get_db()

    rows             = _query_pengeluaran(db, bulan, tahun, filter_kategori or None)
    kategori_summary = _query_kategori_summary(db, bulan, tahun)
    total_pengeluaran= sum(r['jumlah'] for r in rows)
    kategori_terbanyak = kategori_summary[0]['kategori'] if kategori_summary else None
    pemasukan_bln    = _query_pemasukan(db, bulan, tahun)

    # Daftar kategori untuk dropdown filter
    kategori_list = [r['kategori'] for r in db.execute(
        "SELECT DISTINCT COALESCE(kategori,'Lainnya') AS kategori FROM pengeluaran ORDER BY kategori"
    ).fetchall()]

    return render_template('laporan/pengeluaran.html',
        rows=rows,
        bulan=bulan,
        tahun=tahun,
        tahun_list=_tahun_list_pengeluaran(db),
        kategori_list=kategori_list,
        filter_kategori=filter_kategori,
        total_pengeluaran=total_pengeluaran,
        kategori_summary=kategori_summary,
        kategori_terbanyak=kategori_terbanyak,
        pemasukan_bln=pemasukan_bln,
    )


# ── 5. Export Pengeluaran CSV ──────────────────────────────────────────────
@laporan_bp.route('/pengeluaran/export/csv')
@login_required
def export_pengeluaran_csv():
    bulan, tahun = _get_filter_params()
    db   = get_db()
    rows = _query_pengeluaran(db, bulan, tahun)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['No', 'Tanggal', 'Kategori', 'Keterangan', 'Jumlah (Rp)'])
    for i, r in enumerate(rows, 1):
        writer.writerow([i, r['tanggal'], r['kategori'] or 'Lainnya',
                         r['keterangan'] or '', r['jumlah']])
    total = sum(r['jumlah'] for r in rows)
    writer.writerow(['', '', '', 'TOTAL', total])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv', as_attachment=True,
                     download_name=f"laporan_pengeluaran_{bulan:02d}_{tahun}.csv")


# ── 6. Export Pengeluaran PDF ──────────────────────────────────────────────
@laporan_bp.route('/pengeluaran/export/pdf')
@login_required
def export_pengeluaran_pdf():
    bulan, tahun     = _get_filter_params()
    db               = get_db()
    rows             = _query_pengeluaran(db, bulan, tahun)
    kategori_summary = _query_kategori_summary(db, bulan, tahun)
    total_pengeluaran= sum(r['jumlah'] for r in rows)

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               leftMargin=1.5*cm, rightMargin=1.5*cm,
                               topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    story  = _build_header_paragraph(
        'LAPORAN PENGELUARAN KOST',
        f'Periode: {NAMA_BULAN[bulan]} {tahun}', styles)

    # Summary cards
    summary_data = [
        ['Total Transaksi', 'Total Pengeluaran', 'Kategori Terbanyak'],
        [str(len(rows)), fmt_rupiah(total_pengeluaran),
         kategori_summary[0]['kategori'] if kategori_summary else '-'],
    ]
    t_sum = Table(summary_data, colWidths=[5*cm, 6*cm, 7*cm])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,0), MERAH),
        ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
        ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
        ('FONTNAME',      (0,1),(-1,1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0),(-1,-1), 10),
        ('ALIGN',         (0,0),(-1,-1), 'CENTER'),
        ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0),(-1,-1), 7),
        ('BOTTOMPADDING', (0,0),(-1,-1), 7),
        ('GRID',          (0,0),(-1,-1), 0.5, colors.white),
        ('BACKGROUND',    (0,1),(-1,1), colors.HexColor('#fde8d8')),
        ('TEXTCOLOR',     (1,1),(1,1), MERAH),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 0.4*cm))

    # Breakdown per kategori (jika ada)
    if kategori_summary:
        s_h2 = ParagraphStyle('h2', parent=styles['Heading2'],
                               fontSize=11, textColor=BIRU_TUA, spaceAfter=4)
        story.append(Paragraph('Ringkasan per Kategori', s_h2))
        kat_header = ['Kategori', 'Jumlah Transaksi', 'Total (Rp)', 'Persentase']
        kat_data   = [kat_header]
        for ks in kategori_summary:
            pct = (ks['total'] / total_pengeluaran * 100) if total_pengeluaran else 0
            # Hitung jumlah transaksi per kategori
            jml = sum(1 for r in rows if (r['kategori'] or 'Lainnya') == ks['kategori'])
            kat_data.append([ks['kategori'], str(jml), fmt_rupiah(ks['total']), f"{pct:.1f}%"])
        kat_data.append(['', 'TOTAL', fmt_rupiah(total_pengeluaran), '100%'])

        t_kat = Table(kat_data, colWidths=[5*cm, 4*cm, 5*cm, 3*cm])
        ts_kat = _base_style()
        for cmd in _header_cmds(): ts_kat.add(*cmd)
        for cmd in _footer_cmds(len(kat_data)-1): ts_kat.add(*cmd)
        ts_kat.add('ALIGN', (1,1),(3,-1), 'CENTER')
        ts_kat.add('ALIGN', (2,1),(2,-1), 'RIGHT')
        ts_kat.add('TEXTCOLOR', (2,1),(2,-2), MERAH)
        ts_kat.add('FONTNAME', (2,1),(2,-2), 'Helvetica-Bold')
        t_kat.setStyle(ts_kat)
        story.append(t_kat)
        story.append(Spacer(1, 0.5*cm))

    # Tabel detail
    s_h2 = ParagraphStyle('h2b', parent=styles['Heading2'],
                           fontSize=11, textColor=BIRU_TUA, spaceAfter=4)
    story.append(Paragraph('Detail Pengeluaran', s_h2))
    det_header = ['No', 'Tanggal', 'Kategori', 'Keterangan', 'Jumlah (Rp)']
    det_data   = [det_header]
    for i, r in enumerate(rows, 1):
        det_data.append([
            str(i), r['tanggal'],
            r['kategori'] or 'Lainnya',
            r['keterangan'] or '-',
            fmt_rupiah(r['jumlah'])
        ])
    det_data.append(['', '', '', 'TOTAL', fmt_rupiah(total_pengeluaran)])

    t_det = Table(det_data, colWidths=[1*cm, 3*cm, 3.5*cm, 7*cm, 4*cm], repeatRows=1)
    ts_det = _base_style()
    for cmd in _header_cmds(): ts_det.add(*cmd)
    for cmd in _footer_cmds(len(det_data)-1): ts_det.add(*cmd)
    ts_det.add('ALIGN', (4,1),(4,-1), 'RIGHT')
    ts_det.add('TEXTCOLOR', (4,1),(4,-2), MERAH)
    ts_det.add('FONTNAME',  (4,1),(4,-2), 'Helvetica-Bold')
    t_det.setStyle(ts_det)
    story.append(t_det)

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f"laporan_pengeluaran_{bulan:02d}_{tahun}.pdf")
