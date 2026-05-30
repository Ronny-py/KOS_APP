"""
routes/kamar_pdf_routes.py
Generate laporan PDF detail kamar — mencakup info kamar, riwayat penghuni,
komplain, tagihan, dan pembayaran.
Endpoint:
  GET /kamar/<int:penghuni_id>/pdf          → laporan kamar terisi
  GET /kamar/kosong/<nomor_kamar>/pdf       → laporan kamar kosong
  GET /kamar/semua/pdf                      → laporan ringkasan semua kamar
"""
from flask import Blueprint, make_response, abort, request
from utils.auth import login_required
from models.database import get_db
from datetime import date
from .kamar_routes import _hitung_lama_tinggal, SEMUA_KAMAR, HARGA_SEWA_DEFAULT

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.platypus.flowables import HRFlowable
from io import BytesIO

kamar_pdf_bp = Blueprint('kamar_pdf', __name__, url_prefix='/kamar')

# ── Warna tema ──────────────────────────────────────────────────────────────
C_PRIMARY   = colors.HexColor('#6366f1')   # indigo
C_SUCCESS   = colors.HexColor('#16a34a')   # hijau
C_DANGER    = colors.HexColor('#dc2626')   # merah
C_WARN      = colors.HexColor('#d97706')   # kuning/oranye
C_MUTED     = colors.HexColor('#6b7280')   # abu
C_DARK      = colors.HexColor('#111827')   # hampir hitam
C_SURFACE   = colors.HexColor('#1f2937')   # surface gelap
C_LIGHT     = colors.HexColor('#f3f4f6')   # abu terang (bg tabel)
C_BORDER    = colors.HexColor('#374151')   # border gelap
C_WHITE     = colors.white
C_BLACK     = colors.black

# ── Helper format rupiah ────────────────────────────────────────────────────
def rp(n):
    try:
        return f"Rp {int(n or 0):,}".replace(',', '.')
    except Exception:
        return "Rp 0"

def fmt_date(s):
    if not s:
        return "—"
    try:
        return date.fromisoformat(str(s)[:10]).strftime('%d %b %Y')
    except Exception:
        return str(s)


# ── Style helpers ───────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()

    def ps(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=9, leading=13,
                        textColor=C_DARK, spaceAfter=2)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    return {
        'title'    : ps('title',    fontName='Helvetica-Bold', fontSize=18,
                        textColor=C_PRIMARY, spaceAfter=4, leading=22),
        'subtitle' : ps('subtitle', fontName='Helvetica', fontSize=10,
                        textColor=C_MUTED, spaceAfter=12),
        'h2'       : ps('h2',       fontName='Helvetica-Bold', fontSize=12,
                        textColor=C_PRIMARY, spaceBefore=14, spaceAfter=6,
                        leading=15),
        'h3'       : ps('h3',       fontName='Helvetica-Bold', fontSize=10,
                        textColor=C_DARK, spaceBefore=8, spaceAfter=4),
        'body'     : ps('body'),
        'muted'    : ps('muted',    textColor=C_MUTED, fontSize=8),
        'badge_ok' : ps('badge_ok', fontName='Helvetica-Bold', fontSize=8,
                        textColor=C_SUCCESS),
        'badge_err': ps('badge_err',fontName='Helvetica-Bold', fontSize=8,
                        textColor=C_DANGER),
        'badge_warn':ps('badge_warn',fontName='Helvetica-Bold',fontSize=8,
                        textColor=C_WARN),
        'badge_muted':ps('badge_muted',fontName='Helvetica-Bold',fontSize=8,
                        textColor=C_MUTED),
        'mono'     : ps('mono',     fontName='Courier', fontSize=9),
        'right'    : ps('right',    alignment=TA_RIGHT, fontName='Helvetica-Bold',
                        fontSize=9),
        'center'   : ps('center',   alignment=TA_CENTER, fontSize=8,
                        textColor=C_MUTED),
    }


def _tbl_style(header_bg=None, row_stripe=True):
    """Default TableStyle dengan header berwarna dan stripe baris."""
    hbg = header_bg or C_PRIMARY
    cmds = [
        ('BACKGROUND',   (0, 0), (-1, 0), hbg),
        ('TEXTCOLOR',    (0, 0), (-1, 0), C_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 6),
        ('TOPPADDING',   (0, 0), (-1, 0), 6),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [C_WHITE, C_LIGHT] if row_stripe else [C_WHITE]),
        ('GRID',         (0, 0), (-1, -1), 0.4, C_BORDER),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
    ]
    return TableStyle(cmds)


def _section_title(text, st):
    return [
        Spacer(1, 6),
        Paragraph(text, st['h2']),
        HRFlowable(width='100%', thickness=1, color=C_PRIMARY, spaceAfter=6),
    ]


def _kv_table(pairs, st, col_w=None):
    """Key-value 2-kolom (label : nilai)."""
    col_w = col_w or [55*mm, 95*mm]
    data  = [[Paragraph(k, st['muted']), Paragraph(str(v), st['body'])]
             for k, v in pairs]
    tbl = Table(data, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ('FONTNAME',     (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1,-1), 8),
        ('TEXTCOLOR',    (0, 0), (0, -1), C_MUTED),
        ('BOTTOMPADDING',(0, 0), (-1,-1), 4),
        ('TOPPADDING',   (0, 0), (-1,-1), 4),
        ('VALIGN',       (0, 0), (-1,-1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1,-1), 4),
        ('RIGHTPADDING', (0, 0), (-1,-1), 4),
        ('ROWBACKGROUNDS',(0,0), (-1,-1), [C_WHITE, C_LIGHT]),
    ]))
    return tbl


def _footer_text(now_str):
    return f"Dicetak: {now_str}  •  Sistem Manajemen Kost"


# ── PDF builder utama: kamar terisi ─────────────────────────────────────────
def _build_detail_pdf(penghuni, tagihan_list, pembayaran_list,
                      komplain_list, riwayat_kamar, notif_list,
                      total_tagihan, total_terbayar):
    buf = BytesIO()
    W, H = A4
    margin = 20*mm

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin,  bottomMargin=margin + 10,
    )

    now_str = date.today().strftime('%d %B %Y')
    st = _styles()
    story = []

    # ── HEADER ────────────────────────────────────────────────────────────
    header_data = [[
        Paragraph(f"LAPORAN DETAIL KAMAR {penghuni['nomor_kamar']}", st['title']),
        Paragraph(f"Dicetak: {now_str}", ParagraphStyle(
            'hdr_right', fontName='Helvetica', fontSize=8,
            textColor=C_MUTED, alignment=TA_RIGHT)),
    ]]
    hdr_tbl = Table(header_data, colWidths=[130*mm, 50*mm])
    hdr_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('LEFTPADDING',  (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING',(0,0), (-1,-1), 0),
    ]))
    story.append(hdr_tbl)
    story.append(HRFlowable(width='100%', thickness=2, color=C_PRIMARY, spaceAfter=10))

    # ── INFO PENGHUNI ─────────────────────────────────────────────────────
    story += _section_title("Informasi Penghuni", st)

    lama = _hitung_lama_tinggal(penghuni.get('tanggal_masuk'))
    pairs = [
        ("Nama Penghuni",    penghuni.get('nama', '—')),
        ("Nomor Kamar",      penghuni.get('nomor_kamar', '—')),
        ("No. HP",           penghuni.get('no_hp') or '—'),
        ("Tanggal Masuk",    fmt_date(penghuni.get('tanggal_masuk'))),
        ("Lama Tinggal",     lama),
        ("Harga Sewa",       rp(penghuni.get('harga_sewa', 0))),
        ("Deposit",          rp(penghuni.get('deposit', 0))),
        ("Status",           "Aktif"),
        ("Catatan",          penghuni.get('catatan') or '—'),
    ]
    story.append(_kv_table(pairs, st))

    # ── RINGKASAN KEUANGAN ────────────────────────────────────────────────
    story += _section_title("Ringkasan Keuangan", st)

    jumlah_belum = sum(1 for t in tagihan_list if t['status'] != 'lunas')
    jumlah_lunas = sum(1 for t in tagihan_list if t['status'] == 'lunas')
    sisa_total   = total_tagihan - total_terbayar

    fin_data = [
        ["Keterangan", "Jumlah"],
        ["Total Tagihan (semua bulan)",  rp(total_tagihan)],
        ["Total Terbayar",               rp(total_terbayar)],
        ["Sisa Belum Dibayar",           rp(sisa_total)],
        ["Tagihan Lunas",                f"{jumlah_lunas} bulan"],
        ["Tagihan Belum Lunas",          f"{jumlah_belum} bulan"],
    ]
    fin_tbl = Table(fin_data, colWidths=[100*mm, 80*mm])
    fin_style = _tbl_style()
    # warnai baris sisa merah kalau ada
    if sisa_total > 0:
        fin_style.add('TEXTCOLOR', (1, 3), (1, 3), C_DANGER)
        fin_style.add('FONTNAME',  (1, 3), (1, 3), 'Helvetica-Bold')
    else:
        fin_style.add('TEXTCOLOR', (1, 3), (1, 3), C_SUCCESS)
        fin_style.add('FONTNAME',  (1, 3), (1, 3), 'Helvetica-Bold')
    fin_tbl.setStyle(fin_style)
    story.append(fin_tbl)

    # ── RIWAYAT TAGIHAN ───────────────────────────────────────────────────
    story += _section_title("Riwayat Tagihan", st)

    if tagihan_list:
        tag_data = [["Bulan", "Jumlah Tagihan", "Terbayar", "Sisa", "Status", "Jatuh Tempo"]]
        for t in tagihan_list:
            status_txt = t['status'].upper() if t.get('status') else '—'
            color_key  = 'lunas' if t.get('status') == 'lunas' else 'belum'
            tag_data.append([
                t.get('bulan', '—'),
                rp(t.get('jumlah', 0)),
                rp(t.get('total_bayar', 0)),
                rp(t.get('sisa', 0)),
                status_txt,
                fmt_date(t.get('jatuh_tempo')),
            ])
        tag_tbl = Table(tag_data, colWidths=[22*mm, 32*mm, 28*mm, 28*mm, 22*mm, 28*mm])
        ts = _tbl_style()
        # Warnai kolom status
        for i, t in enumerate(tagihan_list, start=1):
            if t.get('status') == 'lunas':
                ts.add('TEXTCOLOR', (4, i), (4, i), C_SUCCESS)
                ts.add('FONTNAME',  (4, i), (4, i), 'Helvetica-Bold')
            elif t.get('status') == 'sebagian':
                ts.add('TEXTCOLOR', (4, i), (4, i), C_WARN)
                ts.add('FONTNAME',  (4, i), (4, i), 'Helvetica-Bold')
            else:
                ts.add('TEXTCOLOR', (4, i), (4, i), C_DANGER)
                ts.add('FONTNAME',  (4, i), (4, i), 'Helvetica-Bold')
        tag_tbl.setStyle(ts)
        story.append(tag_tbl)
    else:
        story.append(Paragraph("Tidak ada data tagihan.", st['muted']))

    # ── RIWAYAT PEMBAYARAN ────────────────────────────────────────────────
    story += _section_title("Riwayat Pembayaran", st)

    if pembayaran_list:
        pay_data = [["Tanggal Bayar", "Bulan", "Jumlah Bayar", "Metode", "Catatan"]]
        for p in pembayaran_list:
            pay_data.append([
                fmt_date(p.get('tanggal_bayar')),
                p.get('bulan', '—'),
                rp(p.get('jumlah_bayar', 0)),
                (p.get('metode_bayar') or '—').title(),
                Paragraph(str(p.get('catatan') or '—'), st['muted']),
            ])
        pay_tbl = Table(pay_data, colWidths=[28*mm, 22*mm, 32*mm, 24*mm, 54*mm])
        pay_tbl.setStyle(_tbl_style(header_bg=C_SUCCESS))
        story.append(pay_tbl)
    else:
        story.append(Paragraph("Tidak ada data pembayaran.", st['muted']))

    # ── KOMPLAIN ──────────────────────────────────────────────────────────
    story += _section_title("Riwayat Komplain", st)

    if komplain_list:
        kpl_data = [["Tanggal", "Judul / Kategori", "Deskripsi", "Status"]]
        for k in komplain_list:
            status = (k.get('status') or '—').replace('_', ' ').title()
            kpl_data.append([
                fmt_date(k.get('created_at') or k.get('tanggal')),
                Paragraph(str(k.get('judul') or k.get('kategori') or '—'), st['body']),
                Paragraph(str(k.get('deskripsi') or '—')[:180], st['muted']),
                status,
            ])
        kpl_tbl = Table(kpl_data, colWidths=[25*mm, 38*mm, 72*mm, 25*mm])
        ts = _tbl_style(header_bg=C_WARN)
        for i, k in enumerate(komplain_list, start=1):
            s = (k.get('status') or '').lower()
            if s in ('selesai', 'ditutup'):
                ts.add('TEXTCOLOR', (3, i), (3, i), C_SUCCESS)
            elif s in ('proses', 'diproses'):
                ts.add('TEXTCOLOR', (3, i), (3, i), C_WARN)
            else:
                ts.add('TEXTCOLOR', (3, i), (3, i), C_DANGER)
            ts.add('FONTNAME', (3, i), (3, i), 'Helvetica-Bold')
        kpl_tbl.setStyle(ts)
        story.append(kpl_tbl)
    else:
        story.append(Paragraph("Tidak ada komplain.", st['muted']))

    # ── RIWAYAT KAMAR (checkin/checkout sebelumnya) ───────────────────────
    if riwayat_kamar:
        story += _section_title("Riwayat Penghuni Kamar Sebelumnya", st)
        rwt_data = [["Nama", "Masuk", "Keluar", "Lama (hari)", "Harga Sewa", "Kondisi Kamar"]]
        for r in riwayat_kamar:
            hari = r.get('lama_tinggal_hari')
            rwt_data.append([
                str(r.get('nama') or '—'),
                fmt_date(r.get('tanggal_masuk')),
                fmt_date(r.get('tanggal_keluar')),
                str(hari) if hari else '—',
                rp(r.get('harga_sewa', 0)),
                str(r.get('kondisi_kamar') or '—')[:30],
            ])
        rwt_tbl = Table(rwt_data, colWidths=[36*mm, 24*mm, 24*mm, 20*mm, 28*mm, 28*mm])
        rwt_tbl.setStyle(_tbl_style(header_bg=C_MUTED))
        story.append(rwt_tbl)

    # ── NOTIFIKASI WA ─────────────────────────────────────────────────────
    if notif_list:
        story += _section_title("Riwayat Notifikasi WhatsApp", st)
        ntf_data = [["Tanggal Kirim", "Jenis", "Status", "Pesan"]]
        for n in notif_list[:30]:
            ntf_data.append([
                fmt_date(n.get('tanggal_kirim')),
                str(n.get('jenis') or '—').replace('_', ' ').title(),
                str(n.get('status') or '—').title(),
                Paragraph(str(n.get('pesan') or '—')[:120], st['muted']),
            ])
        ntf_tbl = Table(ntf_data, colWidths=[27*mm, 30*mm, 20*mm, 83*mm])
        ntf_tbl.setStyle(_tbl_style(header_bg=colors.HexColor('#25D366')))
        story.append(ntf_tbl)

    # ── FOOTER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width='100%', thickness=0.5, color=C_BORDER))
    story.append(Paragraph(_footer_text(now_str), st['center']))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── PDF builder: kamar kosong ────────────────────────────────────────────────
def _build_kosong_pdf(kamar, riwayat_penghuni, komplain_list, pembayaran_list):
    buf = BytesIO()
    margin = 20*mm
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin+10)
    now_str = date.today().strftime('%d %B %Y')
    st = _styles()
    story = []

    # HEADER
    story.append(Paragraph(
        f"LAPORAN KAMAR KOSONG — {kamar['nomor_kamar']}", st['title']))
    story.append(HRFlowable(width='100%', thickness=2, color=C_PRIMARY, spaceAfter=10))

    # INFO KAMAR
    story += _section_title("Informasi Kamar", st)
    hari_kosong = kamar.get('hari_kosong')
    pairs = [
        ("Nomor Kamar",      kamar['nomor_kamar']),
        ("Tipe",             kamar.get('tipe_kamar', 'Standard AC')),
        ("Luas",             f"{kamar.get('luas', 3.5)} m\xb2"),
        ("Kapasitas",        f"{kamar.get('kapasitas', 1)} orang"),
        ("Harga Sewa",       rp(kamar.get('harga_sewa', HARGA_SEWA_DEFAULT))),
        ("Status",           "Kosong"),
        ("Kosong Sejak",     kamar.get('tanggal_kosong') or '—'),
        ("Durasi Kosong",    f"{hari_kosong} hari" if hari_kosong else '—'),
        ("Terakhir Diisi",   kamar.get('terakhir_diisi') or 'Belum pernah'),
        ("Fasilitas",        kamar.get('fasilitas') or '—'),
    ]
    story.append(_kv_table(pairs, st))

    # RIWAYAT PENGHUNI
    story += _section_title("Riwayat Penghuni", st)
    if riwayat_penghuni:
        rwt_data = [["Nama", "Masuk", "Keluar", "Lama Tinggal", "Harga Sewa"]]
        for r in riwayat_penghuni:
            rwt_data.append([
                str(r.get('nama') or '—'),
                str(r.get('tanggal_masuk') or '—'),
                str(r.get('tanggal_keluar') or '—'),
                str(r.get('lama_tinggal') or '—'),
                rp(r.get('harga_sewa', 0)),
            ])
        rwt_tbl = Table(rwt_data, colWidths=[44*mm, 28*mm, 28*mm, 28*mm, 32*mm])
        rwt_tbl.setStyle(_tbl_style(header_bg=C_MUTED))
        story.append(rwt_tbl)
    else:
        story.append(Paragraph("Belum pernah ada penghuni.", st['muted']))

    # KOMPLAIN
    story += _section_title("Riwayat Komplain Kamar", st)
    if komplain_list:
        kpl_data = [["Tanggal", "Judul / Kategori", "Deskripsi", "Status"]]
        for k in komplain_list:
            kpl_data.append([
                fmt_date(k.get('created_at') or k.get('tanggal')),
                Paragraph(str(k.get('judul') or k.get('kategori') or '—'), st['body']),
                Paragraph(str(k.get('deskripsi') or '—')[:180], st['muted']),
                str(k.get('status') or '—').title(),
            ])
        kpl_tbl = Table(kpl_data, colWidths=[25*mm, 38*mm, 72*mm, 25*mm])
        kpl_tbl.setStyle(_tbl_style(header_bg=C_WARN))
        story.append(kpl_tbl)
    else:
        story.append(Paragraph("Tidak ada komplain tercatat.", st['muted']))

    # PEMBAYARAN HISTORIS
    if pembayaran_list:
        story += _section_title("Riwayat Pembayaran (penghuni sebelumnya)", st)
        pay_data = [["Tanggal Bayar", "Penghuni", "Bulan", "Jumlah Bayar", "Metode"]]
        for p in pembayaran_list:
            pay_data.append([
                fmt_date(p.get('tanggal_bayar')),
                str(p.get('nama_penghuni') or '—'),
                str(p.get('bulan') or '—'),
                rp(p.get('jumlah_bayar', 0)),
                str(p.get('metode_bayar') or '—').title(),
            ])
        pay_tbl = Table(pay_data, colWidths=[28*mm, 40*mm, 22*mm, 30*mm, 24*mm - 4])
        pay_tbl.setStyle(_tbl_style(header_bg=C_SUCCESS))
        story.append(pay_tbl)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width='100%', thickness=0.5, color=C_BORDER))
    story.append(Paragraph(_footer_text(now_str), st['center']))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── PDF builder: ringkasan semua kamar ───────────────────────────────────────
def _build_semua_pdf(kamar_list, bulan_ini):
    buf = BytesIO()
    margin = 18*mm
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin+10)
    now_str = date.today().strftime('%d %B %Y')
    st = _styles()
    story = []

    story.append(Paragraph("LAPORAN RINGKASAN SEMUA KAMAR", st['title']))
    story.append(Paragraph(f"Periode: {bulan_ini}  •  Dicetak: {now_str}", st['subtitle']))
    story.append(HRFlowable(width='100%', thickness=2, color=C_PRIMARY, spaceAfter=12))

    # Statistik singkat
    jml_lunas    = sum(1 for k in kamar_list if k.get('status_bayar') == 'lunas')
    jml_belum    = sum(1 for k in kamar_list if k.get('status_bayar') == 'belum')
    jml_sebagian = sum(1 for k in kamar_list if k.get('status_bayar') == 'sebagian')
    jml_kosong   = sum(1 for k in kamar_list if k.get('status_kamar') == 'kosong')
    total_tag    = sum(k.get('jumlah_tagihan') or 0 for k in kamar_list)
    total_bayar  = sum(k.get('total_bayar') or 0 for k in kamar_list)

    stat_data = [
        ["Total Kamar", "Terisi", "Kosong", "Lunas", "Belum/Sebagian", "Total Tagihan", "Total Terbayar"],
        [
            str(len(kamar_list)),
            str(len(kamar_list) - jml_kosong),
            str(jml_kosong),
            str(jml_lunas),
            str(jml_belum + jml_sebagian),
            rp(total_tag),
            rp(total_bayar),
        ]
    ]
    stat_tbl = Table(stat_data, colWidths=[22*mm, 18*mm, 18*mm, 18*mm, 28*mm, 34*mm, 34*mm])
    stat_tbl.setStyle(_tbl_style(header_bg=C_PRIMARY))
    story.append(stat_tbl)
    story.append(Spacer(1, 14))

    # Tabel detail semua kamar
    story += _section_title("Detail Semua Kamar", st)
    tbl_data = [["No.", "Kamar", "Penghuni", "Lama Tinggal", "Harga Sewa",
                 "Tagihan", "Terbayar", "Sisa", "Status", "Komplain"]]

    for i, k in enumerate(kamar_list, 1):
        is_kosong = k.get('status_kamar') == 'kosong'
        status    = 'KOSONG' if is_kosong else (k.get('status_bayar') or '—').upper()
        tbl_data.append([
            str(i),
            k.get('nomor_kamar', '—'),
            str(k.get('nama') or '—') if not is_kosong else '—',
            str(k.get('lama_tinggal') or '—') if not is_kosong else '—',
            rp(k.get('harga_sewa', 0)),
            rp(k.get('jumlah_tagihan', 0)) if not is_kosong else '—',
            rp(k.get('total_bayar', 0))    if not is_kosong else '—',
            rp(k.get('sisa_bayar', 0))     if not is_kosong else '—',
            status,
            str(k.get('komplain_aktif', 0)) if not is_kosong else '—',
        ])

    # Kolom lebar disesuaikan A4 portrait
    col_w = [9*mm, 16*mm, 32*mm, 22*mm, 22*mm, 22*mm, 22*mm, 22*mm, 18*mm, 16*mm]
    big_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
    ts = _tbl_style(header_bg=C_PRIMARY)
    for i, k in enumerate(kamar_list, 1):
        st_k = (k.get('status_bayar') or '').lower()
        is_k = k.get('status_kamar') == 'kosong'
        if is_k:
            ts.add('TEXTCOLOR', (8, i), (8, i), C_PRIMARY)
        elif st_k == 'lunas':
            ts.add('TEXTCOLOR', (8, i), (8, i), C_SUCCESS)
        elif st_k == 'sebagian':
            ts.add('TEXTCOLOR', (8, i), (8, i), C_WARN)
        elif st_k == 'belum':
            ts.add('TEXTCOLOR', (8, i), (8, i), C_DANGER)
        ts.add('FONTNAME', (8, i), (8, i), 'Helvetica-Bold')
        # Komplain merah kalau ada
        if not is_k and (k.get('komplain_aktif') or 0) > 0:
            ts.add('TEXTCOLOR', (9, i), (9, i), C_DANGER)
            ts.add('FONTNAME',  (9, i), (9, i), 'Helvetica-Bold')
    big_tbl.setStyle(ts)
    story.append(big_tbl)

    # Kamar kosong detail
    kosong_list = [k for k in kamar_list if k.get('status_kamar') == 'kosong']
    if kosong_list:
        story += _section_title("Detail Kamar Kosong", st)
        kos_data = [["Nomor Kamar", "Kosong Sejak (hari)", "Terakhir Diisi", "Harga Sewa"]]
        for k in kosong_list:
            hari = k.get('hari_kosong')
            kos_data.append([
                k.get('nomor_kamar', '—'),
                f"{hari} hari" if hari else '—',
                str(k.get('terakhir_diisi') or 'Belum pernah'),
                rp(k.get('harga_sewa', HARGA_SEWA_DEFAULT)),
            ])
        kos_tbl = Table(kos_data, colWidths=[35*mm, 45*mm, 45*mm, 35*mm - 4])
        ts2 = _tbl_style(header_bg=colors.HexColor('#6366f1'))
        for i, k in enumerate(kosong_list, 1):
            hari = k.get('hari_kosong') or 0
            if hari > 30:
                ts2.add('TEXTCOLOR', (1, i), (1, i), C_WARN)
                ts2.add('FONTNAME',  (1, i), (1, i), 'Helvetica-Bold')
        kos_tbl.setStyle(ts2)
        story.append(kos_tbl)

    # Kamar dengan komplain aktif
    komplain_kamar = [k for k in kamar_list
                      if not k.get('status_kamar') == 'kosong'
                      and (k.get('komplain_aktif') or 0) > 0]
    if komplain_kamar:
        story += _section_title("Kamar dengan Komplain Aktif", st)
        kpl_data = [["Nomor Kamar", "Penghuni", "Jumlah Komplain Aktif"]]
        for k in komplain_kamar:
            kpl_data.append([
                k.get('nomor_kamar', '—'),
                str(k.get('nama') or '—'),
                str(k.get('komplain_aktif', 0)),
            ])
        kpl_tbl = Table(kpl_data, colWidths=[40*mm, 80*mm, 40*mm])
        ts3 = _tbl_style(header_bg=C_WARN)
        kpl_tbl.setStyle(ts3)
        story.append(kpl_tbl)

    # Tunggakan terbanyak
    tunggakan = sorted(
        [k for k in kamar_list if not k.get('status_kamar') == 'kosong'
         and (k.get('tagihan_belum') or 0) > 0],
        key=lambda x: x.get('tagihan_belum', 0), reverse=True
    )
    if tunggakan:
        story += _section_title("Kamar dengan Tunggakan", st)
        tng_data = [["Nomor Kamar", "Penghuni", "Tunggakan (bulan)", "Sisa Tagihan"]]
        for k in tunggakan:
            tng_data.append([
                k.get('nomor_kamar', '—'),
                str(k.get('nama') or '—'),
                str(k.get('tagihan_belum', 0)),
                rp(k.get('sisa_bayar', 0)),
            ])
        tng_tbl = Table(tng_data, colWidths=[35*mm, 60*mm, 40*mm, 40*mm - 4])
        ts4 = _tbl_style(header_bg=C_DANGER)
        tng_tbl.setStyle(ts4)
        story.append(tng_tbl)

    # ── RINGKASAN PER KAMAR ───────────────────────────────────────────────────
    story.append(PageBreak())
    story += _section_title("Ringkasan Per Kamar", st)

    for k in kamar_list:
        is_kosong = k.get('status_kamar') == 'kosong'
        nomor     = k.get('nomor_kamar', '—')

        # Warna header card tergantung status
        if is_kosong:
            card_color = C_MUTED
        elif k.get('status_bayar') == 'lunas':
            card_color = C_SUCCESS
        elif k.get('status_bayar') == 'sebagian':
            card_color = C_WARN
        else:
            card_color = C_DANGER if k.get('status_bayar') == 'belum' else C_PRIMARY

        # Judul kamar (baris berwarna)
        judul_data = [[
            Paragraph(f"Kamar {nomor}", ParagraphStyle(
                'card_hdr', fontName='Helvetica-Bold', fontSize=10,
                textColor=C_WHITE, leading=14)),
            Paragraph(
                "KOSONG" if is_kosong else (k.get('status_bayar') or '—').upper(),
                ParagraphStyle('card_status', fontName='Helvetica-Bold', fontSize=9,
                               textColor=C_WHITE, alignment=TA_RIGHT, leading=14)),
        ]]
        judul_tbl = Table(judul_data, colWidths=[130*mm, 45*mm])
        judul_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), card_color),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # Baris detail isi kamar
        if is_kosong:
            hari = k.get('hari_kosong')
            detail_pairs = [
                ("Status Kamar",   "Kosong"),
                ("Kosong Selama",  f"{hari} hari" if hari else "—"),
                ("Terakhir Diisi", k.get('terakhir_diisi') or "Belum pernah"),
                ("Harga Sewa",     rp(k.get('harga_sewa', 0))),
            ]
        else:
            detail_pairs = [
                ("Penghuni",         str(k.get('nama') or '—')),
                ("No. HP",           str(k.get('no_hp') or '—')),
                ("Lama Tinggal",     str(k.get('lama_tinggal') or '—')),
                ("Harga Sewa",       rp(k.get('harga_sewa', 0))),
                ("Tagihan Bulan Ini",rp(k.get('jumlah_tagihan', 0))),
                ("Terbayar",         rp(k.get('total_bayar', 0))),
                ("Sisa Tagihan",     rp(k.get('sisa_bayar', 0))),
                ("Tunggakan (bln)",  str(k.get('tagihan_belum', 0))),
                ("Komplain Aktif",   str(k.get('komplain_aktif', 0))),
            ]

        col_w_kv = [45*mm, 130*mm]
        kv_rows  = []
        for label, val in detail_pairs:
            # Warnai sisa merah kalau ada, komplain merah kalau >0
            val_style = st['body']
            if label == "Sisa Tagihan" and k.get('sisa_bayar', 0) > 0:
                val_style = ParagraphStyle('rv', fontName='Helvetica-Bold', fontSize=9,
                                           textColor=C_DANGER, leading=13)
            elif label == "Komplain Aktif" and int(k.get('komplain_aktif', 0)) > 0:
                val_style = ParagraphStyle('rv2', fontName='Helvetica-Bold', fontSize=9,
                                           textColor=C_WARN, leading=13)
            kv_rows.append([
                Paragraph(label, st['muted']),
                Paragraph(str(val), val_style),
            ])

        detail_tbl = Table(kv_rows, colWidths=col_w_kv)
        detail_tbl.setStyle(TableStyle([
            ('FONTNAME',      (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1,-1), 8),
            ('TEXTCOLOR',     (0, 0), (0, -1), C_MUTED),
            ('BOTTOMPADDING', (0, 0), (-1,-1), 3),
            ('TOPPADDING',    (0, 0), (-1,-1), 3),
            ('LEFTPADDING',   (0, 0), (-1,-1), 8),
            ('RIGHTPADDING',  (0, 0), (-1,-1), 8),
            ('ROWBACKGROUNDS',(0, 0), (-1,-1), [C_WHITE, C_LIGHT]),
            ('GRID',          (0, 0), (-1,-1), 0.3, C_BORDER),
            ('VALIGN',        (0, 0), (-1,-1), 'MIDDLE'),
        ]))

        story.append(KeepTogether([
            judul_tbl,
            detail_tbl,
            Spacer(1, 8),
        ]))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width='100%', thickness=0.5, color=C_BORDER))
    story.append(Paragraph(_footer_text(now_str), st['center']))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Flask routes ─────────────────────────────────────────────────────────────
@kamar_pdf_bp.route('/<int:penghuni_id>/pdf')
@login_required
def detail_pdf(penghuni_id):
    """Unduh laporan PDF detail satu kamar (penghuni aktif)."""
    conn = get_db()

    penghuni = conn.execute(
        "SELECT * FROM penghuni WHERE id = ? AND aktif = 1", (penghuni_id,)
    ).fetchone()
    if not penghuni:
        abort(404)
    penghuni = dict(penghuni)

    tagihan_rows = conn.execute("""
        SELECT t.*, COALESCE(SUM(pb.jumlah_bayar),0) AS total_bayar
        FROM tagihan t
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE t.penghuni_id = ?
        GROUP BY t.id ORDER BY t.bulan DESC
    """, (penghuni_id,)).fetchall()
    tagihan_list = []
    for t in tagihan_rows:
        d = dict(t); d['sisa'] = d['jumlah'] - d['total_bayar']
        tagihan_list.append(d)

    pembayaran_list = [dict(r) for r in conn.execute("""
        SELECT pb.*, t.bulan FROM pembayaran pb
        JOIN tagihan t ON t.id = pb.tagihan_id
        WHERE pb.penghuni_id = ? ORDER BY pb.tanggal_bayar DESC
    """, (penghuni_id,)).fetchall()]

    notif_list = [dict(r) for r in conn.execute("""
        SELECT * FROM notif_wa WHERE penghuni_id = ?
        ORDER BY tanggal_kirim DESC LIMIT 30
    """, (penghuni_id,)).fetchall()]

    komplain_list = [dict(r) for r in conn.execute("""
        SELECT * FROM komplain WHERE nomor_kamar = ?
        ORDER BY created_at DESC
    """, (penghuni['nomor_kamar'],)).fetchall()]

    # Riwayat kamar (checkout + penghuni nonaktif)
    riwayat_kamar = []
    seen = set()
    for r in conn.execute("""
        SELECT c.penghuni_id, c.nama, c.tanggal_masuk, c.tanggal_keluar,
               c.lama_tinggal_hari, c.harga_sewa, c.kondisi_kamar
        FROM checkout c WHERE c.nomor_kamar = ?
        ORDER BY c.tanggal_keluar DESC
    """, (penghuni['nomor_kamar'],)).fetchall():
        d = dict(r); seen.add(d['penghuni_id']); riwayat_kamar.append(d)
    for r in conn.execute("""
        SELECT id AS penghuni_id, nama, tanggal_masuk, tanggal_keluar,
               NULL AS lama_tinggal_hari, harga_sewa, NULL AS kondisi_kamar
        FROM penghuni WHERE nomor_kamar = ? AND aktif = 0 AND id != ?
        ORDER BY tanggal_keluar DESC
    """, (penghuni['nomor_kamar'], penghuni_id)).fetchall():
        d = dict(r)
        if d['penghuni_id'] not in seen:
            if d['tanggal_masuk'] and d['tanggal_keluar']:
                try:
                    m = date.fromisoformat(d['tanggal_masuk'][:10])
                    k = date.fromisoformat(d['tanggal_keluar'][:10])
                    d['lama_tinggal_hari'] = (k - m).days
                except Exception:
                    pass
            riwayat_kamar.append(d)

    conn.close()

    total_tagihan  = sum(t['jumlah']      for t in tagihan_list)
    total_terbayar = sum(t['total_bayar'] for t in tagihan_list)

    pdf_bytes = _build_detail_pdf(
        penghuni, tagihan_list, pembayaran_list,
        komplain_list, riwayat_kamar, notif_list,
        total_tagihan, total_terbayar,
    )

    fname = f"laporan_kamar_{penghuni['nomor_kamar']}_{date.today()}.pdf"
    resp  = make_response(pdf_bytes)
    resp.headers['Content-Type']        = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    return resp


@kamar_pdf_bp.route('/kosong/<nomor_kamar>/pdf')
@login_required
def detail_kosong_pdf(nomor_kamar):
    """Unduh laporan PDF kamar kosong."""
    conn = get_db()
    today = date.today()

    checkout_rows = conn.execute("""
        SELECT nama, tanggal_masuk, tanggal_keluar,
               lama_tinggal_hari, harga_sewa
        FROM checkout WHERE nomor_kamar = ?
        ORDER BY tanggal_keluar DESC
    """, (nomor_kamar,)).fetchall()

    riwayat_rows = conn.execute("""
        SELECT nama, no_hp, tanggal_masuk, tanggal_keluar, harga_sewa
        FROM penghuni
        WHERE nomor_kamar = ? AND (aktif=0 OR tanggal_keluar IS NOT NULL)
        ORDER BY tanggal_keluar DESC
    """, (nomor_kamar,)).fetchall()

    komplain_list = [dict(r) for r in conn.execute("""
        SELECT * FROM komplain WHERE nomor_kamar = ?
        ORDER BY created_at DESC
    """, (nomor_kamar,)).fetchall()]

    pembayaran_list = [dict(r) for r in conn.execute("""
        SELECT pb.*, t.bulan, p.nama AS nama_penghuni
        FROM pembayaran pb
        JOIN tagihan t ON t.id = pb.tagihan_id
        JOIN penghuni p ON p.id = pb.penghuni_id
        WHERE p.nomor_kamar = ? ORDER BY pb.tanggal_bayar DESC
    """, (nomor_kamar,)).fetchall()]

    conn.close()

    # Merge riwayat
    riwayat_penghuni = []
    seen = set()
    for r in list(checkout_rows) + list(riwayat_rows):
        r = dict(r)
        key = (r.get('nama'), r.get('tanggal_keluar'))
        if key in seen:
            continue
        seen.add(key)
        if not r.get('lama_tinggal_hari') and r.get('tanggal_masuk') and r.get('tanggal_keluar'):
            try:
                m = date.fromisoformat(r['tanggal_masuk'][:10])
                k = date.fromisoformat(r['tanggal_keluar'][:10])
                r['lama_tinggal_hari'] = (k - m).days
            except Exception:
                pass
        hari = r.get('lama_tinggal_hari') or 0
        bulan = hari // 30
        r['lama_tinggal'] = f"{bulan} bulan" if bulan else f"{hari} hari"
        for f in ('tanggal_masuk', 'tanggal_keluar'):
            if r.get(f):
                try:
                    r[f] = date.fromisoformat(r[f][:10]).strftime('%d %b %Y')
                except Exception:
                    pass
        riwayat_penghuni.append(r)

    # Info kamar
    hari_kosong = tanggal_kosong = terakhir_diisi = None
    tgl_str = (checkout_rows[0]['tanggal_keluar'] if checkout_rows
               else riwayat_rows[0]['tanggal_keluar'] if riwayat_rows else None)
    if tgl_str:
        try:
            tgl = date.fromisoformat(tgl_str[:10])
            hari_kosong    = (today - tgl).days
            tanggal_kosong = tgl.strftime('%d %b %Y')
            terakhir_diisi = tgl.strftime('%b %Y')
        except Exception:
            pass

    kamar = dict(
        nomor_kamar    = nomor_kamar,
        tipe_kamar     = 'Standard AC',
        lantai         = nomor_kamar[0] if nomor_kamar[0].isdigit() else nomor_kamar[:2],
        luas           = 3.5,
        kapasitas      = 1,
        harga_sewa     = HARGA_SEWA_DEFAULT,
        fasilitas      = None,
        hari_kosong    = hari_kosong,
        tanggal_kosong = tanggal_kosong,
        terakhir_diisi = terakhir_diisi,
    )

    pdf_bytes = _build_kosong_pdf(kamar, riwayat_penghuni, komplain_list, pembayaran_list)
    fname = f"laporan_kamar_kosong_{nomor_kamar}_{date.today()}.pdf"
    resp  = make_response(pdf_bytes)
    resp.headers['Content-Type']        = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    return resp


@kamar_pdf_bp.route('/semua/pdf')
@login_required
def semua_pdf():
    """Unduh laporan PDF ringkasan semua kamar."""
    from .kamar_routes import kamar_bp   # noqa: import blueprint untuk reuse logic
    conn = get_db()
    bulan_ini = date.today().strftime('%Y-%m')
    today     = date.today()

    rows = conn.execute("""
        SELECT
            p.id, p.nama, p.nomor_kamar, p.no_hp, p.tanggal_masuk, p.harga_sewa,
            t.status AS status_bayar, t.jumlah AS jumlah_tagihan,
            COALESCE(SUM(pb.jumlah_bayar), 0) AS total_bayar,
            (SELECT COUNT(*) FROM komplain k
             WHERE k.nomor_kamar = p.nomor_kamar
               AND k.status NOT IN ('selesai','ditutup')) AS komplain_aktif,
            (SELECT COUNT(*) FROM tagihan tx
             WHERE tx.penghuni_id = p.id AND tx.status = 'belum') AS tagihan_belum
        FROM penghuni p
        LEFT JOIN tagihan t ON t.penghuni_id = p.id AND t.bulan = ?
        LEFT JOIN pembayaran pb ON pb.tagihan_id = t.id
        WHERE p.aktif = 1 GROUP BY p.id
    """, (bulan_ini,)).fetchall()
    penghuni_map = {r['nomor_kamar']: dict(r) for r in rows}

    checkout_map = {}
    for row in conn.execute("SELECT nomor_kamar, MAX(tanggal_keluar) AS tgl FROM checkout GROUP BY nomor_kamar").fetchall():
        checkout_map[row['nomor_kamar']] = row['tgl']
    for row in conn.execute("SELECT nomor_kamar, MAX(tanggal_keluar) AS tgl FROM penghuni WHERE aktif=0 AND tanggal_keluar IS NOT NULL GROUP BY nomor_kamar").fetchall():
        if row['nomor_kamar'] not in checkout_map:
            checkout_map[row['nomor_kamar']] = row['tgl']
    conn.close()

    kamar_list = []
    for nomor in SEMUA_KAMAR:
        if nomor in penghuni_map:
            p = penghuni_map[nomor]
            p['lama_tinggal'] = _hitung_lama_tinggal(p['tanggal_masuk'])
            p['sisa_bayar']   = (p['jumlah_tagihan'] or 0) - p['total_bayar']
            p['status_kamar'] = 'isi'
            p['hari_kosong']  = None
            p['terakhir_diisi'] = None
            kamar_list.append(p)
        else:
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
                'id': None, 'nomor_kamar': nomor, 'status_kamar': 'kosong',
                'nama': None, 'no_hp': None, 'harga_sewa': HARGA_SEWA_DEFAULT,
                'tanggal_masuk': None, 'lama_tinggal': None,
                'status_bayar': None, 'jumlah_tagihan': 0,
                'total_bayar': 0, 'sisa_bayar': 0,
                'tagihan_belum': 0, 'komplain_aktif': 0,
                'hari_kosong': hari_kosong, 'terakhir_diisi': terakhir_diisi,
            })

    pdf_bytes = _build_semua_pdf(kamar_list, bulan_ini)
    fname = f"laporan_semua_kamar_{date.today()}.pdf"
    resp  = make_response(pdf_bytes)
    resp.headers['Content-Type']        = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    return resp
