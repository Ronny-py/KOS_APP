"""
routes/media_kamar2_routes.py
Endpoint untuk galeri atas halaman login.
Membaca foto & video dari folder static/media_kamar2/
"""
import os
from flask import Blueprint, jsonify, current_app, send_from_directory

media_kamar2_bp = Blueprint('media_kamar2', __name__)

# Ekstensi yang didukung
FOTO_EXT  = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
VIDEO_EXT = {'.mp4', '.webm', '.mov', '.ogg'}

def _folder2():
    """Kembalikan path absolut folder media_kamar2."""
    return os.path.join(current_app.root_path, 'static', 'media_kamar2')


@media_kamar2_bp.route('/media-kamar2/list')
def list_media2():
    """Kembalikan JSON daftar file di static/media_kamar2/."""
    folder = _folder2()
    os.makedirs(folder, exist_ok=True)

    files = []
    try:
        for fname in sorted(os.listdir(folder)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in FOTO_EXT:
                files.append({
                    'type': 'foto',
                    'url' : f'/media-kamar2/file/{fname}',
                    'name': fname,
                })
            elif ext in VIDEO_EXT:
                files.append({
                    'type': 'video',
                    'url' : f'/media-kamar2/file/{fname}',
                    'name': fname,
                })
    except Exception as e:
        current_app.logger.warning(f'media_kamar2 list error: {e}')

    return jsonify({'files': files})


@media_kamar2_bp.route('/media-kamar2/file/<path:filename>')
def serve_media2(filename):
    """Sajikan file dari static/media_kamar2/."""
    folder = _folder2()
    return send_from_directory(folder, filename)
