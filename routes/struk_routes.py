"""
routes/struk_routes.py
Endpoint untuk generate struk PDF pembayaran dan kirim ke WA penghuni.

Endpoints:
  GET  /struk/download/<pembayaran_id>   → download PDF langsung
  POST /struk/kirim-wa/<pembayaran_id>   → generate PDF lalu kirim via WA server lokal
  GET  /struk/preview/<pembayaran_id>    → tampilkan PDF di browser (inline)
"""

import os
import io
import datetime
import requests
from flask import (Blueprint, send_file, jsonify,
                   session, redirect, url_for, current_app)

struk_bp = Blueprint('struk', __name__)

# ── Helper: ambil data pembayaran dari DB ─────────────────────────────────────
def _get_pembayaran(pembayaran_id: int) -> dict | None:
    """
    Ambil data pembayaran + penghuni dari database.
    Sesuaikan query dengan skema DB kamu.
    Kembalikan dict atau None jika tidak ditemukan.
    """
    try:
        from models.database import get_db
        db = get_db()
        row = db.execute("""
            SELECT
                p.id,
                p.tanggal_bayar,
                p.jumlah,
                p.metode_bayar,
                p.catatan,
                p.bulan,
                p.tahun,
                p.jenis_tagihan,
                ph.nama          AS nama_penghuni,
                ph.no_kamar,
                ph.no_hp,
                k.nama           AS nama_kost,
                k.alamat         AS alamat_kost
            FROM pembayaran p
            JOIN penghuni   ph ON p.penghuni_id = ph.id
            LEFT JOIN kost  k  ON 1=1
            WHERE p.id = ?
        """, (pembayaran_id,)).fetchone()

        if not row:
            return None

        # Nama bulan Indonesia
        BULAN = ['', 'Januari','Februari','Maret','April','Mei','Juni',
                 'Juli','Agustus','September','Oktober','November','Desember']
        bulan_str = BULAN[int(row['bulan'])] if row['bulan'] else '-'
        tahun_str = str(row['tahun']) if row['tahun'] else ''

        # Format tanggal bayar
        try:
            dt = datetime.datetime.strptime(row['tanggal_bayar'], '%Y-%m-%d')
            tgl_fmt = dt.strftime('%-d ') + BULAN[dt.month] + dt.strftime(' %Y')
        except Exception:
            tgl_fmt = row['tanggal_bayar'] or '-'

        return {
            'nama_kost'      : row['nama_kost']      or 'KostPay',
            'alamat_kost'    : row['alamat_kost']    or '',
            'no_struk'       : f"STR-{row['id']:05d}",
            'tgl_bayar'      : tgl_fmt,
            'nama_penghuni'  : row['nama_penghuni']  or '-',
            'no_kamar'       : row['no_kamar']       or '-',
            'no_hp'          : row['no_hp']          or '',
            'bulan_tagihan'  : f"{bulan_str} {tahun_str}".strip(),
            'jenis_tagihan'  : row['jenis_tagihan']  or 'Sewa Bulanan',
            'jumlah'         : int(row['jumlah']     or 0),
            'metode_bayar'   : row['metode_bayar']   or '-',
            'catatan'        : row['catatan']        or '',
            'admin_nama'     : session.get('admin_nama', 'Admin'),
        }
    except Exception as e:
        current_app.logger.error(f"[struk] DB error: {e}")
        return None


def _buat_pdf(pembayaran_id: int):
    """Ambil data dari DB lalu generate PDF. Return (pdf_bytes, data_dict) atau (None, None)."""
    from utils.struk_pdf import buat_struk_pdf
    data = _get_pembayaran(pembayaran_id)
    if not data:
        return None, None
    return buat_struk_pdf(data), data


# ── Endpoint: Download PDF ────────────────────────────────────────────────────
@struk_bp.route('/struk/download/<int:pembayaran_id>')
def download_struk(pembayaran_id):
    """Download struk PDF ke komputer admin / penghuni."""
    if not session.get('admin_id'):
        return redirect(url_for('auth.login'))

    pdf_bytes, data = _buat_pdf(pembayaran_id)
    if not pdf_bytes:
        return jsonify({'error': 'Data pembayaran tidak ditemukan'}), 404

    nama_file = f"Struk_{data['no_struk']}_{data['nama_penghuni'].replace(' ','_')}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nama_file,
    )


# ── Endpoint: Preview PDF (inline di browser) ─────────────────────────────────
@struk_bp.route('/struk/preview/<int:pembayaran_id>')
def preview_struk(pembayaran_id):
    """Tampilkan struk PDF langsung di browser tanpa download."""
    if not session.get('admin_id'):
        return redirect(url_for('auth.login'))

    pdf_bytes, data = _buat_pdf(pembayaran_id)
    if not pdf_bytes:
        return jsonify({'error': 'Data pembayaran tidak ditemukan'}), 404

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
    )


# ── Endpoint: Kirim via WA ────────────────────────────────────────────────────
@struk_bp.route('/struk/kirim-wa/<int:pembayaran_id>', methods=['POST'])
def kirim_struk_wa(pembayaran_id):
    """
    Generate PDF lalu kirim ke WA penghuni melalui WA server lokal (Node.js).
    Expects WA server berjalan di http://localhost:3000 dengan endpoint:
      POST /send-document  { to, filename, mimetype, data (base64) }
    """
    if not session.get('admin_id'):
        return jsonify({'ok': False, 'msg': 'Unauthorized'}), 401

    pdf_bytes, data = _buat_pdf(pembayaran_id)
    if not pdf_bytes:
        return jsonify({'ok': False, 'msg': 'Data pembayaran tidak ditemukan'}), 404

    no_hp = data.get('no_hp', '').strip()
    if not no_hp:
        return jsonify({'ok': False, 'msg': 'Nomor HP penghuni tidak tersedia'}), 400

    # Normalisasi nomor HP → format internasional tanpa +
    hp = no_hp.replace('+', '').replace('-', '').replace(' ', '')
    if hp.startswith('0'):
        hp = '62' + hp[1:]

    import base64
    pdf_b64  = base64.b64encode(pdf_bytes).decode()
    nama_file = f"Struk_{data['no_struk']}.pdf"

    # Pesan teks pengantar
    pesan = (
        f"Halo *{data['nama_penghuni']}*,\n\n"
        f"Berikut struk pembayaran kost Anda:\n"
        f"• Kamar      : {data['no_kamar']}\n"
        f"• Periode    : {data['bulan_tagihan']}\n"
        f"• Jumlah     : Rp {data['jumlah']:,.0f}".replace(',', '.') + "\n"
        f"• Tgl Bayar  : {data['tgl_bayar']}\n\n"
        f"Terima kasih telah membayar tepat waktu 🙏\n"
        f"— {data['nama_kost']}"
    )

    WA_SERVER = os.environ.get('WA_SERVER_URL', 'http://localhost:3000')

    try:
        # 1. Kirim pesan teks dulu
        r_text = requests.post(
            f'{WA_SERVER}/send-message',
            json={'to': hp, 'message': pesan},
            timeout=15,
        )

        # 2. Kirim dokumen PDF
        r_doc = requests.post(
            f'{WA_SERVER}/send-document',
            json={
                'to'       : hp,
                'filename' : nama_file,
                'mimetype' : 'application/pdf',
                'data'     : pdf_b64,
                'caption'  : f"Struk Pembayaran {data['bulan_tagihan']}",
            },
            timeout=30,
        )

        if r_doc.status_code == 200:
            return jsonify({
                'ok' : True,
                'msg': f"Struk berhasil dikirim ke {no_hp}",
            })
        else:
            err = r_doc.json().get('error', r_doc.text)
            return jsonify({'ok': False, 'msg': f"WA server error: {err}"}), 500

    except requests.exceptions.ConnectionError:
        return jsonify({
            'ok' : False,
            'msg': 'WA server tidak aktif. Aktifkan dulu lewat menu WA Server.',
        }), 503
    except Exception as e:
        current_app.logger.error(f"[struk] kirim WA error: {e}")
        return jsonify({'ok': False, 'msg': str(e)}), 500
