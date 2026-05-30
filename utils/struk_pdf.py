"""
utils/struk_pdf.py
Generate struk pembayaran kost dalam format PDF menggunakan ReportLab.

Cara pakai:
    from utils.struk_pdf import buat_struk_pdf
    pdf_bytes = buat_struk_pdf(data)

Parameter `data` (dict):
    nama_kost       : str   — nama kost / usaha
    alamat_kost     : str   — alamat kost (opsional)
    no_struk        : str   — nomor struk, misal "STR-2025-001"
    tgl_bayar       : str   — tanggal pembayaran, misal "26 Mei 2025"
    nama_penghuni   : str   — nama penghuni
    no_kamar        : str   — nomor kamar
    no_hp           : str   — nomor HP penghuni (opsional, untuk WA)
    bulan_tagihan   : str   — periode tagihan, misal "Mei 2025"
    jenis_tagihan   : str   — misal "Sewa Bulanan"
    jumlah          : int   — nominal (rupiah)
    metode_bayar    : str   — "Transfer Bank", "Tunai", dsb
    catatan         : str   — catatan tambahan (opsional)
    admin_nama      : str   — nama admin / penerima (opsional)
"""

import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas


# ── Warna tema ────────────────────────────────────────────────────────────────
C_DARK   = colors.HexColor('#0f1117')
C_CARD   = colors.HexColor('#1a1d27')
C_ACCENT = colors.HexColor('#4f6ef7')
C_GREEN  = colors.HexColor('#22c55e')
C_MUTED  = colors.HexColor('#8892a4')
C_BORDER = colors.HexColor('#2e3347')
C_WHITE  = colors.white
C_LIGHT  = colors.HexColor('#e2e8f0')


def _rupiah(n: int) -> str:
    """Format angka ke string rupiah, misal 1500000 → 'Rp 1.500.000'"""
    return f"Rp {n:,.0f}".replace(',', '.')


def _wrap_text(c, text: str, x: float, y: float, max_width: float,
               font: str, size: float, color=C_LIGHT) -> float:
    """
    Tulis teks dengan word-wrap sederhana.
    Kembalikan y akhir setelah teks ditulis.
    """
    c.setFont(font, size)
    c.setFillColor(color)
    words = text.split()
    line = ''
    line_height = size * 1.4
    for word in words:
        test = f'{line} {word}'.strip()
        if c.stringWidth(test, font, size) <= max_width:
            line = test
        else:
            c.drawString(x, y, line)
            y -= line_height
            line = word
    if line:
        c.drawString(x, y, line)
        y -= line_height
    return y


def buat_struk_pdf(data: dict) -> bytes:
    """
    Generate struk PDF dan kembalikan bytes-nya.
    Ukuran: A4 potrait, desain gelap ala KostPay.
    """
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)

    # ── Background gelap penuh ────────────────────────────────────────────────
    c.setFillColor(C_DARK)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Header strip ─────────────────────────────────────────────────────────
    header_h = 52 * mm
    c.setFillColor(C_ACCENT)
    c.rect(0, H - header_h, W, header_h, fill=1, stroke=0)

    # Ikon rumah sederhana (unicode rumah tidak tersedia di Helvetica, pakai simbol bintang)
    c.setFillColor(C_WHITE)
    c.setFont('Helvetica-Bold', 28)
    c.drawCentredString(W / 2, H - 20 * mm, data.get('nama_kost', 'KostPay'))

    c.setFont('Helvetica', 10)
    c.setFillColor(colors.HexColor('#c7d2fe'))
    alamat = data.get('alamat_kost', '')
    if alamat:
        c.drawCentredString(W / 2, H - 28 * mm, alamat)

    c.setFont('Helvetica', 9)
    c.drawCentredString(W / 2, H - 36 * mm, 'BUKTI PEMBAYARAN RESMI')

    # ── Nomor struk badge ─────────────────────────────────────────────────────
    badge_y = H - header_h - 12 * mm
    badge_w = 70 * mm
    badge_x = (W - badge_w) / 2
    c.setFillColor(C_CARD)
    c.setStrokeColor(C_ACCENT)
    c.setLineWidth(1.5)
    _roundRect(c, badge_x, badge_y - 8 * mm, badge_w, 14 * mm, 4 * mm)

    c.setFillColor(C_ACCENT)
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(W / 2, badge_y - 2 * mm, data.get('no_struk', 'STR-000'))

    # ── Card utama ────────────────────────────────────────────────────────────
    card_margin = 15 * mm
    card_x = card_margin
    card_y = 30 * mm
    card_w = W - 2 * card_margin
    card_h = badge_y - 16 * mm - card_y
    c.setFillColor(C_CARD)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.5)
    _roundRect(c, card_x, card_y, card_w, card_h, 6 * mm, fill=True, stroke=True)

    # ── Baris info dalam card ─────────────────────────────────────────────────
    inner_x   = card_x + 10 * mm
    inner_w   = card_w - 20 * mm
    right_x   = card_x + card_w - 10 * mm
    row_h     = 9 * mm
    cur_y     = card_y + card_h - 12 * mm

    def _row(label, value, val_color=C_LIGHT, bold_val=False):
        nonlocal cur_y
        c.setFont('Helvetica', 9)
        c.setFillColor(C_MUTED)
        c.drawString(inner_x, cur_y, label)
        val_font = 'Helvetica-Bold' if bold_val else 'Helvetica'
        c.setFont(val_font, 9)
        c.setFillColor(val_color)
        c.drawRightString(right_x, cur_y, str(value))
        cur_y -= row_h

    def _divider():
        nonlocal cur_y
        cur_y -= 2 * mm
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.4)
        c.line(inner_x, cur_y, right_x, cur_y)
        cur_y -= 4 * mm

    # Info penghuni
    _row('Nama Penghuni', data.get('nama_penghuni', '-'))
    _row('Nomor Kamar',   data.get('no_kamar', '-'))
    _row('Tanggal Bayar', data.get('tgl_bayar', '-'))
    _row('Periode',       data.get('bulan_tagihan', '-'))

    _divider()

    # Info tagihan
    _row('Jenis Tagihan', data.get('jenis_tagihan', 'Sewa Bulanan'))
    _row('Metode Bayar',  data.get('metode_bayar', '-'))

    _divider()

    # Total — besar
    cur_y -= 2 * mm
    c.setFont('Helvetica', 10)
    c.setFillColor(C_MUTED)
    c.drawString(inner_x, cur_y, 'TOTAL DIBAYAR')

    jumlah = data.get('jumlah', 0)
    c.setFont('Helvetica-Bold', 16)
    c.setFillColor(C_GREEN)
    c.drawRightString(right_x, cur_y, _rupiah(jumlah))
    cur_y -= 8 * mm

    # Status lunas
    _divider()
    cur_y -= 1 * mm
    status_w = 30 * mm
    status_x = (W - status_w) / 2
    c.setFillColor(colors.HexColor('#052e16'))
    _roundRect(c, status_x, cur_y - 5 * mm, status_w, 9 * mm, 2 * mm, fill=True, stroke=False)
    c.setFillColor(C_GREEN)
    c.setFont('Helvetica-Bold', 9)
    c.drawCentredString(W / 2, cur_y, 'LUNAS')
    cur_y -= 10 * mm

    # Catatan
    catatan = data.get('catatan', '')
    if catatan:
        _divider()
        c.setFont('Helvetica-Oblique', 8)
        c.setFillColor(C_MUTED)
        c.drawString(inner_x, cur_y, f'Catatan: {catatan}')
        cur_y -= row_h

    # Admin
    admin = data.get('admin_nama', '')
    if admin:
        c.setFont('Helvetica', 8)
        c.setFillColor(C_MUTED)
        c.drawString(inner_x, cur_y, f'Diterima oleh: {admin}')

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_y = 18 * mm
    c.setFont('Helvetica', 7.5)
    c.setFillColor(C_MUTED)
    c.drawCentredString(W / 2, footer_y,
        'Struk ini dihasilkan secara otomatis oleh sistem KostPay')
    c.drawCentredString(W / 2, footer_y - 5 * mm,
        f'Dicetak: {datetime.datetime.now().strftime("%d %b %Y, %H:%M")}')

    # Garis dekorasi bawah
    c.setStrokeColor(C_ACCENT)
    c.setLineWidth(2)
    c.line(card_margin, 12 * mm, W - card_margin, 12 * mm)

    c.save()
    buf.seek(0)
    return buf.read()


def _roundRect(c, x, y, w, h, r, fill=True, stroke=False):
    """Gambar persegi panjang dengan sudut membulat."""
    c.roundRect(x, y, w, h, r, fill=int(fill), stroke=int(stroke))
