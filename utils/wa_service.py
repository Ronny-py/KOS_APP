"""
utils/wa_service.py
Layanan pengiriman WhatsApp menggunakan Fonnte API.
https://fonnte.com
"""

import requests
from datetime import datetime
from utils.format_helper import rupiah


# ─── Config Fonnte ───────────────────────────────────────────────────────────

FONNTE_TOKEN = "UMYjheFvUPcVN2TWrxvc"  # Ganti dengan token dari fonnte.com
FONNTE_URL   = "https://api.fonnte.com/send"


# ─── Kirim pesan WhatsApp ────────────────────────────────────────────────────

def kirim_wa(no_hp: str, pesan: str, media_url: str = None) -> tuple:
    """
    Kirim pesan WhatsApp menggunakan Fonnte API.

    Args:
        no_hp     : Nomor HP (format: 08xxx atau 62xxx)
        pesan     : Isi pesan teks
        media_url : URL gambar/file (opsional)

    Returns:
        (success: bool, error_message: str)
    """
    try:
        no_hp = normalize_nomor_hp(no_hp)

        payload = {
            "target":  no_hp,
            "message": pesan,
        }

        if media_url:
            payload["url"] = media_url

        headers = {
            "Authorization": FONNTE_TOKEN
        }

        response = requests.post(
            FONNTE_URL,
            data=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("status") is True:
                return (True, None)
            else:
                return (False, result.get("reason") or result.get("message") or "Unknown error")
        else:
            return (False, f"HTTP {response.status_code}: {response.text}")

    except requests.exceptions.ConnectionError:
        return (False, "Tidak bisa terhubung ke Fonnte API.")
    except requests.exceptions.Timeout:
        return (False, "Request timeout ke Fonnte API.")
    except Exception as e:
        return (False, str(e))


# ─── Normalize nomor HP ──────────────────────────────────────────────────────

def normalize_nomor_hp(no_hp: str) -> str:
    """Normalize nomor HP ke format 62xxx."""
    no_hp = ''.join(filter(str.isdigit, no_hp.strip()))
    if no_hp.startswith('0'):
        no_hp = '62' + no_hp[1:]
    elif not no_hp.startswith('62'):
        no_hp = '62' + no_hp
    return no_hp


# ─── Buat pesan tagihan ──────────────────────────────────────────────────────

def buat_pesan_tagihan(penghuni_data: dict, sisa: float = 0) -> str:
    nama         = penghuni_data.get('nama', '—')
    kamar        = penghuni_data.get('nomor_kamar', '—')
    bulan        = penghuni_data.get('bulan', '—')
    jumlah       = penghuni_data.get('jumlah', 0)
    jatuh_tempo  = penghuni_data.get('tanggal_jatuh_tempo', '—')

    return f"""🏠 *NOTIFIKASI TAGIHAN SEWA KAMAR*

Halo *{nama}*,

Berikut detail tagihan sewa kamar Anda:

📍 Kamar: *{kamar}*
📅 Bulan: *{bulan}*
💰 Jumlah Tagihan: *{rupiah(jumlah)}*
❌ Sisa Pembayaran: *{rupiah(sisa)}*
⏰ Jatuh Tempo: *{jatuh_tempo}*

Mohon segera lakukan pembayaran sebelum tanggal jatuh tempo.
Abaikan jika sudah melakukan pembayaran.

Terima kasih,
*Manajemen Kost*""".strip()


# ─── Buat pesan konfirmasi bayar ─────────────────────────────────────────────

def buat_pesan_konfirmasi_bayar(penghuni_data: dict, jumlah_bayar: float) -> str:
    nama  = penghuni_data.get('nama', '—')
    kamar = penghuni_data.get('nomor_kamar', '—')
    bulan = penghuni_data.get('bulan', '—')

    return f"""✅ *KONFIRMASI PEMBAYARAN*

Halo *{nama}*,

Pembayaran sewa kamar Anda telah dicatat:

📍 Kamar: *{kamar}*
📅 Bulan: *{bulan}*
💳 Nominal: *{rupiah(jumlah_bayar)}*
⏱️ Waktu: *{datetime.now().strftime('%d-%m-%Y %H:%M')}*

Terima kasih telah melakukan pembayaran tepat waktu!

*Manajemen Kost*""".strip()


# ─── Buat pesan custom ───────────────────────────────────────────────────────

def buat_pesan_custom(judul: str, isi: str) -> str:
    return f"""📢 *{judul.upper()}*

{isi}

*Manajemen Kost*""".strip()


# ─── Health check ────────────────────────────────────────────────────────────

def check_wa_server() -> dict:
    """Cek koneksi ke Fonnte API."""
    try:
        response = requests.get("https://api.fonnte.com", timeout=5)
        return {'status': 'ok', 'message': 'Fonnte API terjangkau'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
