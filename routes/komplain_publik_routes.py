"""
routes/komplain_publik_routes.py
Endpoint publik — penghuni submit komplain TANPA login.
"""
import os, uuid
from flask import Blueprint, request, jsonify, current_app
from models import komplain_model

komplain_publik_bp = Blueprint('komplain_publik', __name__)

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'heic'}


def _save_foto(file):
    if not file or file.filename == '':
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return None
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'komplain')
    os.makedirs(folder, exist_ok=True)
    fname = f"komplain_{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(folder, fname))
    return f"komplain/{fname}"


@komplain_publik_bp.route('/api/komplain', methods=['POST'])
def submit_komplain():
    """
    Menerima komplain dari penghuni via chatbot / form publik.
    Multipart form-data:
      nama, kamar, no_hp, kategori, judul, deskripsi, prioritas, foto (optional)
    """
    try:
        nama      = (request.form.get('nama')      or '').strip()
        kamar     = (request.form.get('kamar')     or '').strip()
        no_hp     = (request.form.get('no_hp')     or '').strip()
        kategori  = (request.form.get('kategori')  or 'lainnya').strip()
        judul     = (request.form.get('judul')      or '').strip()
        deskripsi = (request.form.get('deskripsi') or '').strip()
        prioritas = (request.form.get('prioritas') or 'normal').strip()

        if not nama or not kamar or not judul or not deskripsi:
            return jsonify(success=False,
                           reply='⚠️ Nama, nomor kamar, judul, dan deskripsi wajib diisi.'), 400

        foto_path = _save_foto(request.files.get('foto'))

        komplain_model.tambah(nama, kamar, no_hp, kategori, judul, deskripsi, foto_path, prioritas)

        return jsonify(
            success=True,
            reply=(
                f"✅ Komplain kamu sudah diterima!\n\n"
                f"📋 *{judul}*\n"
                f"🏠 Kamar {kamar} — {nama}\n\n"
                f"Admin akan meninjau dan segera merespons.\n"
                f"Pantau status komplain bisa tanya lagi di sini 😊"
            )
        )
    except Exception as e:
        current_app.logger.error(f"[komplain_publik] error: {e}")
        return jsonify(success=False, reply='❌ Terjadi kesalahan. Coba lagi atau hubungi admin.'), 500


@komplain_publik_bp.route('/api/komplain/status', methods=['GET'])
def cek_status():
    """
    Penghuni bisa cek status komplain berdasarkan nama + kamar.
    GET /api/komplain/status?nama=Budi&kamar=A1
    """
    nama  = (request.args.get('nama')  or '').strip()
    kamar = (request.args.get('kamar') or '').strip()
    if not nama or not kamar:
        return jsonify(reply='Sebutkan nama dan nomor kamar kamu untuk cek status komplain.')

    from models.database import get_db
    rows = get_db().execute("""
        SELECT id, judul, status, prioritas, catatan_admin, created_at, updated_at
        FROM komplain
        WHERE LOWER(nama_pelapor) LIKE ? AND LOWER(nomor_kamar) LIKE ?
        ORDER BY created_at DESC LIMIT 5
    """, (f'%{nama.lower()}%', f'%{kamar.lower()}%')).fetchall()

    if not rows:
        return jsonify(reply=f"Tidak ditemukan komplain atas nama *{nama}* kamar *{kamar}*. "
                             f"Coba submit komplain dulu ya 😊")

    STATUS_ICON = {'baru':'🆕','diproses':'🔧','selesai':'✅','ditolak':'❌'}
    lines = [f"📋 *Status Komplain — {nama} / Kamar {kamar}*\n"]
    for r in rows:
        icon = STATUS_ICON.get(r['status'], '❓')
        lines.append(f"{icon} *{r['judul']}*")
        lines.append(f"   Status : {r['status'].upper()}")
        if r['catatan_admin']:
            lines.append(f"   Catatan: {r['catatan_admin']}")
        lines.append(f"   Dibuat : {r['created_at'][:10]}\n")

    return jsonify(reply='\n'.join(lines))
