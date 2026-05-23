"""
utils/wa_service.py
Layanan pengiriman WhatsApp menggunakan WhatsApp.js (wa-web.js).
Pastikan WhatsApp.js server sudah running di endpoint yang sesuai.
"""

import requests
import json
from datetime import datetime
from utils.format_helper import rupiah


# ─── Config WhatsApp.js ──────────────────────────────────────────────────────

WHATSAPP_SERVER_URL = "http://localhost:3000"  # Default WhatsApp.js server
# Sesuaikan dengan port dan host WhatsApp.js Anda

WHATSAPP_API_KEY = "your-api-key-here"  # Jika WhatsApp.js pakai auth
WHATSAPP_INSTANCE_ID = "default"  # Instance ID di WhatsApp.js


# ─── Kirim pesan WhatsApp ────────────────────────────────────────────────────

def kirim_wa(no_hp: str, pesan: str, media_url: str = None) -> tuple:
    """
    Kirim pesan WhatsApp menggunakan WhatsApp.js.
    
    Args:
        no_hp: Nomor HP (format: 62812xxxx atau 082812xxxx)
        pesan: Isi pesan teks
        media_url: URL gambar/file (opsional)
    
    Returns:
        (success: bool, error_message: str)
    """
    try:
        # Normalize nomor HP
        no_hp = normalize_nomor_hp(no_hp)
        
        # Endpoint WhatsApp.js untuk send message
        endpoint = f"{WHATSAPP_SERVER_URL}/api/send-message"
        
        payload = {
            "number": no_hp,
            "message": pesan,
            "instance": WHATSAPP_INSTANCE_ID
        }
        
        # Tambah media jika ada
        if media_url:
            payload["mediaUrl"] = media_url
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Tambah API key jika diperlukan
        if WHATSAPP_API_KEY and WHATSAPP_API_KEY != "your-api-key-here":
            headers["Authorization"] = f"Bearer {WHATSAPP_API_KEY}"
        
        # Send request
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        # Check response
        if response.status_code in [200, 201]:
            result = response.json()
            if result.get('success') or result.get('status') == 'sent':
                return (True, None)
            else:
                error = result.get('message') or result.get('error') or 'Unknown error'
                return (False, error)
        else:
            error = f"HTTP {response.status_code}: {response.text}"
            return (False, error)
    
    except requests.exceptions.ConnectionError:
        return (False, "WhatsApp.js server tidak terhubung. Pastikan server running.")
    except requests.exceptions.Timeout:
        return (False, "Request timeout. Server lambat merespons.")
    except Exception as e:
        return (False, str(e))


# ─── Kirim dengan template ───────────────────────────────────────────────────

def kirim_wa_template(no_hp: str, template_name: str, template_params: dict) -> tuple:
    """
    Kirim pesan WhatsApp menggunakan template (jika WhatsApp.js support).
    
    Args:
        no_hp: Nomor HP
        template_name: Nama template
        template_params: Parameter untuk template
    
    Returns:
        (success: bool, error_message: str)
    """
    try:
        no_hp = normalize_nomor_hp(no_hp)
        
        endpoint = f"{WHATSAPP_SERVER_URL}/api/send-template"
        
        payload = {
            "number": no_hp,
            "template": template_name,
            "parameters": template_params,
            "instance": WHATSAPP_INSTANCE_ID
        }
        
        headers = {"Content-Type": "application/json"}
        if WHATSAPP_API_KEY and WHATSAPP_API_KEY != "your-api-key-here":
            headers["Authorization"] = f"Bearer {WHATSAPP_API_KEY}"
        
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            if result.get('success'):
                return (True, None)
            else:
                return (False, result.get('message', 'Unknown error'))
        else:
            return (False, f"HTTP {response.status_code}: {response.text}")
    
    except Exception as e:
        return (False, str(e))


# ─── Normalize nomor HP ──────────────────────────────────────────────────────

def normalize_nomor_hp(no_hp: str) -> str:
    """
    Normalize nomor HP ke format international (+62xxx).
    
    Contoh:
        '0812345678' → '+6281234567@s.whatsapp.net'
        '62812345678' → '+6281234567@s.whatsapp.net'
        '812345678' → '+6281234567@s.whatsapp.net'
    """
    # Hapus karakter selain digit
    no_hp = ''.join(filter(str.isdigit, no_hp.strip()))
    
    # Jika mulai dengan 0, ganti dengan 62
    if no_hp.startswith('0'):
        no_hp = '62' + no_hp[1:]
    
    # Jika belum mulai dengan 62, tambahkan
    elif not no_hp.startswith('62'):
        no_hp = '62' + no_hp
    
    # Format untuk WhatsApp: +62xxx atau 62xxx@s.whatsapp.net
    # Beberapa library WhatsApp.js butuh format +6281234567
    return f"+{no_hp}"


# ─── Buat pesan tagihan ──────────────────────────────────────────────────────

def buat_pesan_tagihan(penghuni_data: dict, sisa: float = 0) -> str:
    """
    Format pesan tagihan untuk dikirim via WhatsApp.
    
    Args:
        penghuni_data: Dict dengan kunci: nama, nomor_kamar, no_hp, harga_sewa, bulan, dll
        sisa: Sisa tagihan yang belum dibayar
    
    Returns:
        String pesan siap kirim
    """
    nama = penghuni_data.get('nama', '—')
    kamar = penghuni_data.get('nomor_kamar', '—')
    bulan = penghuni_data.get('bulan', '—')
    jumlah = penghuni_data.get('jumlah', 0)
    
    # Format tanggal jatuh tempo
    jatuh_tempo = penghuni_data.get('tanggal_jatuh_tempo', '—')
    
    pesan = f"""🏠 *NOTIFIKASI TAGIHAN SEWA KAMAR*

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
*Manajemen Kost*
"""
    
    return pesan.strip()


# ─── Buat pesan pembayaran (konfirmasi) ──────────────────────────────────────

def buat_pesan_konfirmasi_bayar(penghuni_data: dict, jumlah_bayar: float) -> str:
    """
    Format pesan konfirmasi pembayaran.
    
    Args:
        penghuni_data: Dict penghuni
        jumlah_bayar: Nominal pembayaran
    
    Returns:
        String pesan konfirmasi
    """
    nama = penghuni_data.get('nama', '—')
    kamar = penghuni_data.get('nomor_kamar', '—')
    bulan = penghuni_data.get('bulan', '—')
    
    pesan = f"""✅ *KONFIRMASI PEMBAYARAN*

Halo *{nama}*,

Pembayaran sewa kamar Anda telah dicatat:

📍 Kamar: *{kamar}*
📅 Bulan: *{bulan}*
💳 Nominal: *{rupiah(jumlah_bayar)}*
⏱️  Waktu: *{datetime.now().strftime('%d-%m-%Y %H:%M')}*

Terima kasih telah melakukan pembayaran tepat waktu!

*Manajemen Kost*
"""
    
    return pesan.strip()


# ─── Buat pesan notifikasi umum ──────────────────────────────────────────────

def buat_pesan_custom(judul: str, isi: str) -> str:
    """
    Format pesan custom/notifikasi umum.
    
    Args:
        judul: Judul pesan
        isi: Isi pesan
    
    Returns:
        String pesan
    """
    pesan = f"""📢 *{judul.upper()}*

{isi}

*Manajemen Kost*
"""
    
    return pesan.strip()


# ─── Health check WhatsApp.js server ─────────────────────────────────────────

def check_wa_server() -> dict:
    """
    Check apakah WhatsApp.js server sedang running.
    
    Returns:
        {'status': 'ok'/'error', 'message': str, 'server_url': str}
    """
    try:
        response = requests.get(
            f"{WHATSAPP_SERVER_URL}/api/health",
            timeout=5
        )
        
        if response.status_code == 200:
            return {
                'status': 'ok',
                'message': 'WhatsApp.js server running',
                'server_url': WHATSAPP_SERVER_URL
            }
        else:
            return {
                'status': 'error',
                'message': f'Server returned {response.status_code}',
                'server_url': WHATSAPP_SERVER_URL
            }
    
    except requests.exceptions.ConnectionError:
        return {
            'status': 'error',
            'message': 'Cannot connect to WhatsApp.js server',
            'server_url': WHATSAPP_SERVER_URL
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'server_url': WHATSAPP_SERVER_URL
        }


# ─── Contoh penggunaan ──────────────────────────────────────────────────────

if __name__ == '__main__':
    # Test kirim pesan
    test_nomor = "081234567890"
    test_pesan = "Halo, ini pesan test dari WhatsApp.js"
    
    print(f"Testing kirim ke {test_nomor}...")
    sukses, error = kirim_wa(test_nomor, test_pesan)
    
    if sukses:
        print("✅ Pesan berhasil dikirim!")
    else:
        print(f"❌ Error: {error}")
    
    # Test health check
    print("\nChecking server...")
    health = check_wa_server()
    print(f"Status: {health['status']}")
    print(f"Message: {health['message']}")
