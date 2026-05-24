"""
routes/wa_server_routes.py
Status WhatsApp via Fonnte API — Node.js tidak digunakan.
"""
import requests
from flask import Blueprint, jsonify
from utils.auth import login_required

wa_server_bp = Blueprint('wa_server', __name__, url_prefix='/wa-server')

# Dummy agar app.py yang lama tidak error saat import
WA_SERVER_DIR = ''
_wa_process   = None


def _is_running() -> bool:
    """Selalu True — tidak ada Node.js server yang perlu dicek."""
    return True


def _wa_ready() -> bool:
    """Cek koneksi ke Fonnte API."""
    try:
        from utils.wa_service import FONNTE_TOKEN
        r = requests.get(
            'https://api.fonnte.com/device',
            headers={'Authorization': FONNTE_TOKEN},
            timeout=5
        )
        data = r.json()
        return data.get('status') is True
    except Exception:
        return False


# ── API endpoints ─────────────────────────────────────────────────────────────

@wa_server_bp.route('/status')
def status():
    """Status koneksi Fonnte — tanpa login."""
    ready = _wa_ready()
    return jsonify({
        'running': True,
        'ready':   ready,
        'url':     'https://api.fonnte.com',
        'mode':    'fonnte',
    })


@wa_server_bp.route('/start', methods=['POST'])
@login_required
def start():
    """Tidak diperlukan — Fonnte tidak butuh start server lokal."""
    return jsonify({
        'success': True,
        'message': 'Menggunakan Fonnte API — tidak perlu start server.'
    })


@wa_server_bp.route('/stop', methods=['POST'])
@login_required
def stop():
    """Tidak diperlukan — Fonnte tidak butuh stop server lokal."""
    return jsonify({
        'success': True,
        'message': 'Menggunakan Fonnte API — tidak ada server lokal untuk dihentikan.'
    })


@wa_server_bp.route('/logs')
@login_required
def logs():
    """Tidak ada log Node.js — kembalikan info Fonnte."""
    return jsonify({
        'lines': ['[Fonnte Mode] Tidak ada log server lokal.']
    })
