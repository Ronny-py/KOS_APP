"""
routes/notif_wa_routes.py
Kelola history dan log notifikasi WhatsApp yang dikirim.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.auth import login_required
from models.database import get_db
from datetime import datetime, timedelta

notif_wa_bp = Blueprint('notif_wa', __name__, url_prefix='/notif-wa')


# ─── List history notifikasi WA ──────────────────────────────────────────────

@notif_wa_bp.route('/')
@login_required
def index():
    """
    Tampilkan history semua notifikasi WhatsApp yang dikirim.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    conn = get_db()
    
    # Total count
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM notif_wa"
    ).fetchone()['cnt']
    
    # Fetch dengan join ke tabel penghuni untuk nama
    rows = conn.execute("""
        SELECT 
            n.id, n.penghuni_id, p.nama, p.no_hp,
            n.pesan, n.status, n.tanggal_kirim, n.error_msg
        FROM notif_wa n
        LEFT JOIN penghuni p ON n.penghuni_id = p.id
        ORDER BY n.tanggal_kirim DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('notif_wa/index.html',
                           notifikasi=rows,
                           page=page,
                           total_pages=total_pages,
                           total=total)


# ─── Detail notifikasi WA ────────────────────────────────────────────────────

@notif_wa_bp.route('/detail/<int:notif_id>')
@login_required
def detail(notif_id):
    """
    Tampilkan detail satu notifikasi WA.
    """
    conn = get_db()
    notif = conn.execute("""
        SELECT 
            n.id, n.penghuni_id, p.nama, p.no_hp, p.email,
            n.pesan, n.status, n.tanggal_kirim, n.tanggal_update, n.error_msg
        FROM notif_wa n
        LEFT JOIN penghuni p ON n.penghuni_id = p.id
        WHERE n.id = ?
    """, (notif_id,)).fetchone()
    conn.close()
    
    if not notif:
        flash('Notifikasi tidak ditemukan.', 'danger')
        return redirect(url_for('notif_wa.index'))
    
    return render_template('notif_wa/detail.html', notif=dict(notif))


# ─── Filter by status ────────────────────────────────────────────────────────

@notif_wa_bp.route('/filter')
@login_required
def filter_by_status():
    """
    Filter notifikasi berdasarkan status: pending, sent, failed.
    """
    status = request.args.get('status', 'sent')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    if status not in ['pending', 'sent', 'failed']:
        status = 'sent'
    
    conn = get_db()
    
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM notif_wa WHERE status = ?",
        (status,)
    ).fetchone()['cnt']
    
    rows = conn.execute("""
        SELECT 
            n.id, n.penghuni_id, p.nama, p.no_hp,
            n.pesan, n.status, n.tanggal_kirim, n.error_msg
        FROM notif_wa n
        LEFT JOIN penghuni p ON n.penghuni_id = p.id
        WHERE n.status = ?
        ORDER BY n.tanggal_kirim DESC
        LIMIT ? OFFSET ?
    """, (status, per_page, offset)).fetchall()
    
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('notif_wa/index.html',
                           notifikasi=rows,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           filter_status=status)


# ─── Hapus notifikasi lama (cleanup) ─────────────────────────────────────────

@notif_wa_bp.route('/cleanup', methods=['POST'])
@login_required
def cleanup():
    """
    Hapus notifikasi yang lebih dari 30 hari lalu.
    """
    try:
        cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
        
        conn = get_db()
        result = conn.execute(
            "DELETE FROM notif_wa WHERE tanggal_kirim < ?",
            (cutoff_date,)
        )
        deleted = result.rowcount
        conn.commit()
        conn.close()
        
        flash(f'✓ {deleted} notifikasi lama berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'❌ Gagal: {e}', 'danger')
    
    return redirect(url_for('notif_wa.index'))


# ─── API: Get summary stats ──────────────────────────────────────────────────

@notif_wa_bp.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    """
    Return JSON stats: total, sent, failed, pending.
    """
    conn = get_db()
    
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending
        FROM notif_wa
    """).fetchone()
    
    conn.close()
    
    return jsonify({
        'total': stats['total'] or 0,
        'sent': stats['sent'] or 0,
        'failed': stats['failed'] or 0,
        'pending': stats['pending'] or 0
    })
