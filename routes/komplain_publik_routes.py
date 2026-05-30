"""
routes/komplain_publik_routes.py
Endpoint publik — penghuni submit komplain TANPA login.
"""
import os, uuid
from flask import Blueprint, request, jsonify, current_app, render_template
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


@komplain_publik_bp.route('/komplain-publik', methods=['GET'])
def form_komplain():
    """Halaman form komplain publik — tanpa login, tanpa sidebar."""
    return render_template(
        'komplain/komplain_publik.html',
        KATEGORI_LIST=komplain_model.KATEGORI_LIST,
        PRIORITAS_LIST=komplain_model.PRIORITAS_LIST,
    )


# Nilai kategori AC di DB adalah 'ac' (sesuai komplain_model.KATEGORI_LIST)
_KATEGORI_AC = {'ac', 'pendingin', 'air conditioner'}

def _is_komplain_ac(kategori: str, judul: str, deskripsi: str) -> bool:
    """
    Mendeteksi apakah komplain berkaitan dengan AC.
    Cek kategori (nilai DB: 'ac'), atau kata kunci di judul/deskripsi.
    """
    if (kategori or '').lower() in _KATEGORI_AC:
        return True
    teks = f"{judul} {deskripsi}".lower()
    return any(kw in teks for kw in (' ac ', 'ac ', ' ac', 'air conditioner', 'pendingin ruangan', 'a/c'))


def _get_service_ac_terakhir(kamar: str) -> str | None:
    """
    Cari tanggal selesai service AC terakhir untuk kamar tertentu.
    Nilai kategori AC di DB: 'ac'. Mengembalikan string tanggal (YYYY-MM-DD)
    atau None jika belum pernah ada.
    """
    from models.database import get_db
    try:
        row = get_db().execute(
            """
            SELECT selesai_at, updated_at
            FROM   komplain
            WHERE  UPPER(TRIM(nomor_kamar)) = UPPER(TRIM(?))
              AND  LOWER(kategori)          = 'ac'
              AND  status                   = 'selesai'
            ORDER  BY COALESCE(selesai_at, updated_at) DESC
            LIMIT  1
            """,
            (kamar,)
        ).fetchone()

        if not row:
            return None

        # Utamakan selesai_at, fallback ke updated_at
        tanggal_raw = row['selesai_at'] or row['updated_at']
        return tanggal_raw[:10] if tanggal_raw else None
    except Exception as e:
        current_app.logger.warning(f"[service_ac] gagal query: {e}")
        return None


@komplain_publik_bp.route('/api/komplain', methods=['POST'])
def submit_komplain():
    """
    Menerima komplain dari penghuni via chatbot / form publik.
    Multipart form-data:
      nama, kamar, no_hp, kategori, judul, deskripsi, prioritas, foto (optional)
    Jika komplain terkait AC, respons menyertakan tanggal service AC terakhir
    yang sudah selesai untuk kamar tersebut.
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

        # ── Susun reply ──────────────────────────────────────────────────────
        reply_lines = [
            f"✅ Komplain kamu sudah diterima!\n",
            f"📋 *{judul}*",
            f"🏠 Kamar {kamar} — {nama}\n",
        ]

        # Sisipkan info service AC terakhir jika komplain terkait AC
        if _is_komplain_ac(kategori, judul, deskripsi):
            tgl_service = _get_service_ac_terakhir(kamar)
            if tgl_service:
                reply_lines.append(
                    f"❄️ *Info:* Service AC terakhir yang selesai untuk kamar {kamar} "
                    f"adalah pada *{tgl_service}*.\n"
                    f"Mohon info ini bisa membantu admin mendiagnosa masalah lebih cepat."
                )
            else:
                reply_lines.append(
                    f"❄️ *Info:* AC kamar {kamar} belum pernah service."
                )
            reply_lines.append("")  # baris kosong sebelum penutup

        reply_lines += [
            "Admin akan meninjau dan segera merespons.",
            "Pantau status komplain bisa tanya lagi di sini 😊",
        ]

        return jsonify(success=True, reply="\n".join(reply_lines))

    except Exception as e:
        current_app.logger.error(f"[komplain_publik] error: {e}")
        return jsonify(success=False, reply='❌ Terjadi kesalahan. Coba lagi atau hubungi admin.'), 500


@komplain_publik_bp.route('/api/validasi-penghuni', methods=['POST'])
def validasi_penghuni():
    """
    Validasi nama + nomor kamar sebelum submit komplain.
    Request JSON: { "nama": "Tania", "kamar": "104" }
    Response:     { "valid": true/false }
    """
    from models.database import get_db
    data  = request.get_json(silent=True) or {}
    nama  = (data.get('nama')  or '').strip()
    kamar = (data.get('kamar') or '').strip()

    if not nama or not kamar:
        return jsonify(valid=False)

    row = get_db().execute(
        '''SELECT id FROM penghuni
           WHERE LOWER(TRIM(nama))        = LOWER(?)
             AND UPPER(TRIM(nomor_kamar)) = UPPER(?)
             AND aktif = 1
           LIMIT 1''',
        (nama, kamar)
    ).fetchone()

    return jsonify(valid=(row is not None))


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
