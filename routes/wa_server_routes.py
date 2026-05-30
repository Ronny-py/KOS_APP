"""
routes/wa_server_routes.py
Start / stop / status WhatsApp.js server (Node.js) dari dalam Flask.
"""
import subprocess
import os
import sys
import requests
from flask import Blueprint, jsonify, current_app
from utils.auth import login_required

wa_server_bp = Blueprint('wa_server', __name__, url_prefix='/wa-server')

# Path ke folder wa-server (satu level di atas folder Flask)
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WA_SERVER_DIR = os.path.join(BASE_DIR, 'wa-server')
WA_SERVER_URL = 'http://localhost:3000'

# Simpan referensi proses agar bisa di-stop
_wa_process = None


def _is_running() -> bool:
    """Cek apakah WA server merespons."""
    try:
        r = requests.get(f'{WA_SERVER_URL}/api/health', timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _wa_ready() -> bool:
    """Cek apakah WhatsApp sudah ter-scan (isReady=true)."""
    try:
        r = requests.get(f'{WA_SERVER_URL}/api/status', timeout=3)
        return r.json().get('ready', False)
    except Exception:
        return False


# ── API endpoints ─────────────────────────────────────────────────────────────

@wa_server_bp.route('/status')
def status():
    """Status server — bisa diakses tanpa login (untuk halaman pre-login)."""
    running = _is_running()
    ready   = _wa_ready() if running else False
    return jsonify({
        'running': running,
        'ready':   ready,
        'url':     WA_SERVER_URL,
    })


@wa_server_bp.route('/start', methods=['POST'])
@login_required
def start():
    global _wa_process
    if _is_running():
        return jsonify({'success': True, 'message': 'Server sudah berjalan.'})

    server_js = os.path.join(WA_SERVER_DIR, 'server.js')
    if not os.path.isfile(server_js):
        return jsonify({'success': False,
                        'message': f'server.js tidak ditemukan di {WA_SERVER_DIR}'}), 404

    try:
        # Jalankan `node server.js` di background, stdout/stderr ke PIPE
        _wa_process = subprocess.Popen(
            ['node', 'server.js'],
            cwd=WA_SERVER_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # Windows: sembunyikan jendela CMD
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
        return jsonify({'success': True, 'message': 'WA server sedang distart...'})
    except FileNotFoundError:
        return jsonify({'success': False,
                        'message': 'Node.js tidak ditemukan. Pastikan Node.js sudah terinstall.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@wa_server_bp.route('/stop', methods=['POST'])
@login_required
def stop():
    global _wa_process
    if _wa_process and _wa_process.poll() is None:
        _wa_process.terminate()
        try:
            _wa_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _wa_process.kill()
        _wa_process = None
        return jsonify({'success': True, 'message': 'WA server dihentikan.'})

    # Fallback: kill via port (jika distart di luar Flask)
    if sys.platform == 'win32':
        os.system('FOR /F "tokens=5" %P IN (\'netstat -aon ^| findstr :3000\') DO taskkill /F /PID %P >nul 2>&1')
    else:
        os.system('kill $(lsof -ti:3000) 2>/dev/null')

    return jsonify({'success': True, 'message': 'WA server dihentikan.'})


@wa_server_bp.route('/logs')
@login_required
def logs():
    """Ambil beberapa baris log terakhir dari proses (jika ada)."""
    global _wa_process
    output = []
    if _wa_process and _wa_process.stdout:
        import select, io
        # Non-blocking read: baca apa yang sudah ada di buffer
        if sys.platform != 'win32':
            import select
            while True:
                r, _, _ = select.select([_wa_process.stdout], [], [], 0)
                if not r:
                    break
                line = _wa_process.stdout.readline()
                if line:
                    output.append(line.rstrip())
                else:
                    break
    return jsonify({'lines': output[-50:]})  # max 50 baris
