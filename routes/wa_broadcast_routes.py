"""
wa_broadcast_routes.py
Broadcast WhatsApp ke penghuni kos.
- Delay antar pesan dapat dikonfigurasi admin (min & max detik)
- SSE streaming untuk progress real-time
"""
import json
import queue as _queue
import random
import threading
import time
import uuid

import requests
from flask import Blueprint, Response, current_app, jsonify, request, session, stream_with_context

from models.database import get_db

wa_broadcast_bp = Blueprint('wa_broadcast', __name__, url_prefix='/wa/broadcast')

WA_API_URL        = 'http://localhost:3000/api/send-message'
DEFAULT_MIN_DELAY = 5    # detik — fallback jika admin tidak mengisi
DEFAULT_MAX_DELAY = 12

# In-memory job store
# { job_id: { 'rows', 'pesan_tmpl', 'no_hp_kosong', 'delay_min', 'delay_max', 'queue' } }
_jobs: dict = {}


def _login_required():
    if not session.get('admin_id'):
        return jsonify({'success': False, 'message': 'Login diperlukan'}), 401
    return None


# ── GET /wa/broadcast/penghuni ────────────────────────────────────────────────
@wa_broadcast_bp.route('/penghuni')
def get_penghuni():
    err = _login_required()
    if err:
        return err

    db   = get_db()
    rows = db.execute(
        """
        SELECT id, nama, nomor_kamar, no_hp
        FROM   penghuni
        WHERE  aktif = 1
        ORDER  BY CAST(nomor_kamar AS INTEGER), nomor_kamar
        """
    ).fetchall()

    return jsonify({
        'success':  True,
        'penghuni': [
            {'id': r['id'], 'nama': r['nama'],
             'nomor_kamar': r['nomor_kamar'], 'no_hp': r['no_hp'] or ''}
            for r in rows
        ]
    })


# ── POST /wa/broadcast/kirim ──────────────────────────────────────────────────
@wa_broadcast_bp.route('/kirim', methods=['POST'])
def kirim_broadcast():
    err = _login_required()
    if err:
        return err

    data       = request.get_json(force=True) or {}
    ids        = data.get('ids', [])
    pesan_tmpl = (data.get('pesan') or '').strip()

    # ── Delay dari admin — clamp ke range aman 1-60 detik ─────────────────
    def _safe_int(val, default):
        try:
            return max(1, min(60, int(val)))
        except (ValueError, TypeError):
            return default

    delay_min = _safe_int(data.get('delay_min'), DEFAULT_MIN_DELAY)
    delay_max = _safe_int(data.get('delay_max'), DEFAULT_MAX_DELAY)
    if delay_min > delay_max:           # swap jika terbalik
        delay_min, delay_max = delay_max, delay_min

    if not pesan_tmpl:
        return jsonify({'success': False, 'message': 'Pesan tidak boleh kosong'}), 400

    db = get_db()

    if ids:
        placeholders = ','.join('?' * len(ids))
        rows = db.execute(
            f"SELECT id, nama, nomor_kamar, no_hp FROM penghuni "
            f"WHERE aktif=1 AND id IN ({placeholders})", ids
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, nama, nomor_kamar, no_hp FROM penghuni WHERE aktif=1"
        ).fetchall()

    if not rows:
        return jsonify({'success': False, 'message': 'Tidak ada penghuni yang dipilih'}), 400

    no_hp_kosong = [r['nama'] for r in rows if not r['no_hp']]
    rows_valid   = [dict(r) for r in rows if r['no_hp']]

    job_id = uuid.uuid4().hex[:10]
    _jobs[job_id] = {
        'rows':         rows_valid,
        'pesan_tmpl':   pesan_tmpl,
        'no_hp_kosong': no_hp_kosong,
        'delay_min':    delay_min,
        'delay_max':    delay_max,
        'queue':        _SafeQueue(),
    }

    app = current_app._get_current_object()
    threading.Thread(
        target=_process_broadcast, args=(job_id, app), daemon=True
    ).start()

    return jsonify({
        'success':       True,
        'job_id':        job_id,
        'total':         len(rows_valid),
        'no_hp_kosong':  no_hp_kosong,
        'delay_min':     delay_min,
        'delay_max':     delay_max,
    })


# ── GET /wa/broadcast/stream/<job_id>  (SSE) ─────────────────────────────────
@wa_broadcast_bp.route('/stream/<job_id>')
def stream_broadcast(job_id):
    job = _jobs.get(job_id)
    if not job:
        def _err():
            yield f"data: {json.dumps({'type':'error','message':'Job tidak ditemukan'})}\n\n"
        return Response(stream_with_context(_err()), mimetype='text/event-stream')

    def generate():
        q = job['queue']
        while True:
            evt = q.get()
            yield f"data: {json.dumps(evt)}\n\n"
            if evt.get('type') in ('done', 'error'):
                threading.Timer(60, lambda: _jobs.pop(job_id, None)).start()
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Background worker ─────────────────────────────────────────────────────────
def _process_broadcast(job_id: str, app):
    with app.app_context():
        job        = _jobs[job_id]
        rows       = job['rows']
        pesan_tmpl = job['pesan_tmpl']
        delay_min  = job['delay_min']
        delay_max  = job['delay_max']
        q          = job['queue']
        db         = get_db()

        sent_ok = sent_fail = 0

        for i, r in enumerate(rows):
            # ── Delay acak sesuai setting admin ───────────────────────────────
            if i > 0:
                delay = round(random.uniform(delay_min, delay_max), 1)
                q.put({
                    'type':  'waiting',
                    'index': i,
                    'total': len(rows),
                    'delay': delay,
                    'next':  r['nama'],
                })
                time.sleep(delay)

            # ── Render pesan ───────────────────────────────────────────────────
            pesan = (
                pesan_tmpl
                .replace('{nama}',  r['nama'] or '')
                .replace('{kamar}', r['nomor_kamar'] or '')
                .replace('{no_hp}', r['no_hp'] or '')
            )

            status  = 'failed'
            err_msg = None
            try:
                resp = requests.post(
                    WA_API_URL,
                    json={'number': r['no_hp'], 'message': pesan},
                    timeout=20,
                )
                rd = resp.json()
                if resp.status_code == 200 and rd.get('success'):
                    status = 'sent';  sent_ok  += 1
                else:
                    err_msg = rd.get('message', 'Unknown error'); sent_fail += 1
            except Exception as e:
                err_msg = str(e); sent_fail += 1

            # ── Log ke DB ──────────────────────────────────────────────────────
            try:
                db.execute(
                    "INSERT INTO notif_wa (penghuni_id, pesan, status, error_msg) "
                    "VALUES (?, ?, ?, ?)",
                    (r['id'], pesan, status, err_msg)
                )
                db.commit()
            except Exception:
                pass

            # ── SSE event progress ─────────────────────────────────────────────
            q.put({
                'type':        'progress',
                'index':       i + 1,
                'total':       len(rows),
                'nama':        r['nama'],
                'nomor_kamar': r['nomor_kamar'],
                'no_hp':       r['no_hp'],
                'status':      status,
                'error_msg':   err_msg,
                'sent_ok':     sent_ok,
                'sent_fail':   sent_fail,
            })

        q.put({
            'type':         'done',
            'total':        len(rows),
            'sent_ok':      sent_ok,
            'sent_fail':    sent_fail,
            'no_hp_kosong': job['no_hp_kosong'],
        })


# ── Thread-safe queue ─────────────────────────────────────────────────────────
class _SafeQueue:
    def __init__(self):    self._q = _queue.Queue()
    def put(self, item):   self._q.put(item)
    def get(self):         return self._q.get()
