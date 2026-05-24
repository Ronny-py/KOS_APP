"""
routes/wa_server_routes.py
Status WhatsApp via Fonnte API — Node.js tidak digunakan.
"""
from flask import Blueprint, jsonify
from utils.auth import login_required

wa_server_bp = Blueprint('wa_server', __name__, url_prefix='/wa-server')

WA_SERVER_DIR = ''
_wa_process   = None


def _is_running() -> bool:
    return True


def _wa_ready() -> bool:
    return True  # Fonnte selalu ready selama token valid


@wa_server_bp.route('/status')
def status():
    return jsonify({
        'running': True,
        'ready':   True,
        'url':     'https://api.fonnte.com',
        'mode':    'fonnte',
    })


@wa_server_bp.route('/start', methods=['POST'])
@login_required
def start():
    return jsonify({
        'success': True,
        'message': 'Menggunakan Fonnte API — tidak perlu start server.'
    })


@wa_server_bp.route('/stop', methods=['POST'])
@login_required
def stop():
    return jsonify({
        'success': True,
        'message': 'Menggunakan Fonnte API — tidak ada server lokal.'
    })


@wa_server_bp.route('/logs')
@login_required
def logs():
    return jsonify({
        'lines': ['[Fonnte Mode] Tidak ada log server lokal.']
    })
