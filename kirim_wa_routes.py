"""
routes/kirim_wa_routes.py
Kirim notifikasi WhatsApp ke penghuni (bulk send).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from utils.auth import login_required
from models.database import get_db
from models import penghuni_model
from datetime import date
import json, uuid, threading, time, random

kirim_wa_bp = Blueprint('kirim_wa', __name__, url_prefix='/kirim-wa')


# ─── Halaman interface kirim WA ──────────────────────────────────────────────

@kirim_wa_bp.route('/')
@login_required
def index():
    """
    Halaman untuk kirim notifikasi WA.
    Menampilkan daftar penghuni yang bisa dikirimi WA.
    """
    bulan_ini = date.today().strftime('%Y-%m')
    
    conn = get_db()
    
    # Ambil penghuni aktif yang punya no HP dan tagihan bulan ini yang belum lunas
    penghuni_list = conn.execute("""
        SELECT DISTINCT
            p.id, p.nama, p.no_hp, p.nomor_kamar,
            t.id as tagihan_id, t.bulan, t.status, t.jumlah,
            COALESCE(SUM(pb.jumlah_bayar), 0) as total_bayar
        FROM penghuni p
        LEFT JOIN tagihan t ON p.id = t.penghuni_id AND t.bulan = ?
        LEFT JOIN pembayaran pb ON t.id = pb.tagihan_id
        WHERE p.aktif = 1 AND p.no_hp IS NOT NULL AND p.no_hp != ''
        AND t.id IS NOT NULL AND t.status != 'lunas'
        GROUP BY p.id, t.id
        ORDER BY p.nama
    """, (bulan_ini,)).fetchall()
    
    conn.close()
    
    penghuni_data = []
    for row in penghuni_list:
        sisa = row['jumlah'] - row['total_bayar']
        penghuni_data.append({
            'id': row['id'],
            'nama': row['nama'],
            'no_hp': row['no_hp'],
            'nomor_kamar': row['nomor_kamar'],
            'tagihan_id': row['tagihan_id'],
            'jumlah': row['jumlah'],
            'total_bayar': row['total_bayar'],
            'sisa': sisa,
            'status': row['status']
        })
    
    return render_template('kirim_wa/index.html',
                           penghuni_list=penghuni_data,
                           bulan_ini=bulan_ini)


# ─── Kirim WA ke satu penghuni ──────────────────────────────────────────────

@kirim_wa_bp.route('/send/<int:penghuni_id>', methods=['POST'])
@login_required
def send_to_one(penghuni_id):
    """
    Kirim notifikasi WA ke satu penghuni.
    POST endpoint, return JSON.
    """
    try:
        from utils.wa_service import kirim_wa, buat_pesan_tagihan
        from models import penghuni_model
        
        penghuni = penghuni_model.get_penghuni_by_id(penghuni_id)
        if not penghuni:
            return jsonify({'success': False, 'message': 'Penghuni tidak ditemukan'}), 404
        
        bulan_ini = date.today().strftime('%Y-%m')
        conn = get_db()
        
        tagihan = conn.execute(
            "SELECT * FROM tagihan WHERE penghuni_id=? AND bulan=?",
            (penghuni_id, bulan_ini)
        ).fetchone()
        
        if not tagihan:
            conn.close()
            return jsonify({'success': False, 'message': 'Belum ada tagihan bulan ini'}), 400
        
        if tagihan['status'] == 'lunas':
            conn.close()
            return jsonify({'success': False, 'message': 'Tagihan sudah lunas'}), 400
        
        bayar = conn.execute(
            "SELECT COALESCE(SUM(jumlah_bayar), 0) AS total FROM pembayaran WHERE tagihan_id=?",
            (tagihan['id'],)
        ).fetchone()['total']
        
        sisa = tagihan['jumlah'] - bayar
        row = {**dict(penghuni), **dict(tagihan)}
        
        # Kirim WA
        sukses, err = kirim_wa(penghuni['no_hp'], buat_pesan_tagihan(row, sisa=sisa))
        
        # Log ke tabel notif_wa
        status_log = 'sent' if sukses else 'failed'
        error_msg = err if not sukses else None
        
        conn.execute("""
            INSERT INTO notif_wa (penghuni_id, pesan, status, error_msg)
            VALUES (?, ?, ?, ?)
        """, (penghuni_id, buat_pesan_tagihan(row, sisa=sisa), status_log, error_msg))
        conn.commit()
        conn.close()
        
        if sukses:
            return jsonify({
                'success': True,
                'message': f'✅ WA berhasil dikirim ke {penghuni["nama"]}'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'❌ Gagal kirim WA: {err}'
            }), 500
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# ─── Bulk send WA ───────────────────────────────────────────────────────────

@kirim_wa_bp.route('/bulk-send', methods=['POST'])
@login_required
def bulk_send():
    """
    Kirim notifikasi WA ke multiple penghuni.
    Expect JSON: {'penghuni_ids': [1, 2, 3]}
    """
    try:
        data = request.get_json()
        penghuni_ids = data.get('penghuni_ids', [])
        
        if not penghuni_ids:
            return jsonify({'success': False, 'message': 'Pilih minimal 1 penghuni'}), 400
        
        from utils.wa_service import kirim_wa, buat_pesan_tagihan
        from models import penghuni_model
        
        bulan_ini = date.today().strftime('%Y-%m')
        conn = get_db()
        
        results = {
            'success': [],
            'failed': [],
            'skipped': []
        }
        
        for pid in penghuni_ids:
            try:
                penghuni = penghuni_model.get_penghuni_by_id(pid)
                
                if not penghuni or not penghuni.get('no_hp'):
                    results['skipped'].append({
                        'id': pid,
                        'reason': 'No HP tidak ada atau penghuni tidak ditemukan'
                    })
                    continue
                
                tagihan = conn.execute(
                    "SELECT * FROM tagihan WHERE penghuni_id=? AND bulan=?",
                    (pid, bulan_ini)
                ).fetchone()
                
                if not tagihan or tagihan['status'] == 'lunas':
                    results['skipped'].append({
                        'id': pid,
                        'reason': 'Belum ada tagihan atau sudah lunas'
                    })
                    continue
                
                bayar = conn.execute(
                    "SELECT COALESCE(SUM(jumlah_bayar), 0) AS total FROM pembayaran WHERE tagihan_id=?",
                    (tagihan['id'],)
                ).fetchone()['total']
                
                sisa = tagihan['jumlah'] - bayar
                row = {**dict(penghuni), **dict(tagihan)}
                pesan = buat_pesan_tagihan(row, sisa=sisa)
                
                sukses, err = kirim_wa(penghuni['no_hp'], pesan)
                
                # Log
                status_log = 'sent' if sukses else 'failed'
                error_msg = err if not sukses else None
                
                conn.execute("""
                    INSERT INTO notif_wa (penghuni_id, pesan, status, error_msg)
                    VALUES (?, ?, ?, ?)
                """, (pid, pesan, status_log, error_msg))
                
                if sukses:
                    results['success'].append({
                        'id': pid,
                        'nama': penghuni['nama']
                    })
                else:
                    results['failed'].append({
                        'id': pid,
                        'nama': penghuni['nama'],
                        'error': err
                    })
            
            except Exception as e:
                results['failed'].append({
                    'id': pid,
                    'error': str(e)
                })
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_sent': len(results['success']),
                'total_failed': len(results['failed']),
                'total_skipped': len(results['skipped'])
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# ─── Status pengiriman ───────────────────────────────────────────────────────

@kirim_wa_bp.route('/status/<int:notif_id>')
@login_required
def get_status(notif_id):
    """
    Check status pengiriman notifikasi tertentu.
    Return JSON.
    """
    conn = get_db()
    notif = conn.execute(
        "SELECT id, status, error_msg, tanggal_kirim FROM notif_wa WHERE id=?",
        (notif_id,)
    ).fetchone()
    conn.close()
    
    if not notif:
        return jsonify({'success': False, 'message': 'Notifikasi tidak ditemukan'}), 404
    
    return jsonify({
        'success': True,
        'status': notif['status'],
        'error_msg': notif['error_msg'],
        'tanggal_kirim': notif['tanggal_kirim']
    })


# ─── Broadcast: ambil daftar penghuni ────────────────────────────────────────

@kirim_wa_bp.route('/broadcast/penghuni', endpoint='broadcast_penghuni')
@login_required
def broadcast_penghuni():
    """
    Kembalikan semua penghuni aktif (tanpa filter tagihan/HP)
    untuk keperluan broadcast manual dari halaman status.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT id, nama, nomor_kamar, no_hp
        FROM penghuni
        WHERE aktif = 1
        ORDER BY nomor_kamar
    """).fetchall()
    conn.close()

    penghuni = [
        {
            'id':          r['id'],
            'nama':        r['nama'],
            'nomor_kamar': r['nomor_kamar'],
            'no_hp':       r['no_hp'] or '',
        }
        for r in rows
    ]
    return jsonify({'success': True, 'penghuni': penghuni})


# ─── Broadcast: simpan job di memory ─────────────────────────────────────────

_bc_jobs = {}   # { job_id: { queue: [...], done: bool } }


# ─── Broadcast: kirim ke banyak penghuni (SSE) ───────────────────────────────

@kirim_wa_bp.route('/broadcast/kirim', methods=['POST'], endpoint='broadcast_kirim')
@login_required
def broadcast_kirim():
    """
    Terima { ids: [...], pesan: '...', delay_min: 5, delay_max: 12 }
    ids kosong = kirim ke semua penghuni aktif.
    Jalankan pengiriman di background thread, return { success, job_id, total }.
    """
    data      = request.get_json(silent=True) or {}
    ids       = data.get('ids', [])
    pesan_tpl = data.get('pesan', '').strip()
    delay_min = max(1, int(data.get('delay_min', 5)))
    delay_max = max(delay_min, int(data.get('delay_max', 12)))

    if not pesan_tpl:
        return jsonify({'success': False, 'message': 'Pesan kosong'}), 400

    conn = get_db()
    if ids:
        placeholders = ','.join('?' * len(ids))
        rows = conn.execute(
            f"SELECT id, nama, nomor_kamar, no_hp FROM penghuni "
            f"WHERE aktif=1 AND id IN ({placeholders}) ORDER BY nomor_kamar",
            ids
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, nama, nomor_kamar, no_hp FROM penghuni "
            "WHERE aktif=1 ORDER BY nomor_kamar"
        ).fetchall()
    conn.close()

    targets = [dict(r) for r in rows]
    if not targets:
        return jsonify({'success': False, 'message': 'Tidak ada penghuni yang sesuai'}), 400

    job_id = str(uuid.uuid4())
    _bc_jobs[job_id] = {'queue': [], 'done': False}

    def run():
        from utils.wa_service import kirim_wa
        queue        = _bc_jobs[job_id]['queue']
        sent_ok      = 0
        sent_fail    = 0
        no_hp_kosong = []

        for i, p in enumerate(targets):
            # jeda acak sebelum kirim (kecuali penghuni pertama)
            if i > 0:
                delay = random.uniform(delay_min, delay_max)
                queue.append({
                    'type':  'waiting',
                    'delay': round(delay, 1),
                    'next':  p['nama'],
                    'index': i,
                })
                time.sleep(delay)

            if not p.get('no_hp'):
                no_hp_kosong.append(p['nama'])
                queue.append({
                    'type':        'progress',
                    'index':       i + 1,
                    'nama':        p['nama'],
                    'nomor_kamar': p['nomor_kamar'],
                    'status':      'failed',
                    'error_msg':   'No HP kosong',
                })
                sent_fail += 1
                continue

            pesan = (pesan_tpl
                     .replace('{nama}',  p['nama'])
                     .replace('{kamar}', p['nomor_kamar'])
                     .replace('{no_hp}', p['no_hp']))

            try:
                sukses, err = kirim_wa(p['no_hp'], pesan)
            except Exception as e:
                sukses, err = False, str(e)

            # simpan log ke DB
            try:
                c = get_db()
                c.execute(
                    "INSERT INTO notif_wa (penghuni_id, pesan, status, error_msg) "
                    "VALUES (?, ?, ?, ?)",
                    (p['id'], pesan, 'sent' if sukses else 'failed', None if sukses else err)
                )
                c.commit()
                c.close()
            except Exception:
                pass

            if sukses:
                sent_ok += 1
            else:
                sent_fail += 1

            queue.append({
                'type':        'progress',
                'index':       i + 1,
                'nama':        p['nama'],
                'nomor_kamar': p['nomor_kamar'],
                'status':      'sent' if sukses else 'failed',
                'error_msg':   err or '',
            })

        queue.append({
            'type':         'done',
            'sent_ok':      sent_ok,
            'sent_fail':    sent_fail,
            'no_hp_kosong': no_hp_kosong,
        })
        _bc_jobs[job_id]['done'] = True

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'success': True, 'job_id': job_id, 'total': len(targets)})


# ─── Broadcast: SSE stream progress ─────────────────────────────────────────

@kirim_wa_bp.route('/broadcast/stream/<job_id>', endpoint='broadcast_stream')
@login_required
def broadcast_stream(job_id):
    """SSE stream untuk memantau progress broadcast secara real-time."""
    job = _bc_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job tidak ditemukan'}), 404

    def generate():
        sent = 0
        while True:
            queue = job['queue']
            while sent < len(queue):
                evt = queue[sent]
                sent += 1
                yield f"data: {json.dumps(evt)}\n\n"
            if job['done'] and sent >= len(queue):
                break
            time.sleep(0.1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
