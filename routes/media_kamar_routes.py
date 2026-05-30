"""
routes/media_kamar_routes.py
Melayani file foto & video kamar dari folder static/media_kamar/
dan menyediakan endpoint /media-kamar/list untuk galeri di halaman login.
"""

import os
import json
from flask import Blueprint, send_from_directory, jsonify, current_app

media_kamar_bp = Blueprint('media_kamar', __name__)

# ── Folder tempat menyimpan foto & video kamar ──────────────────────────────
# Letakkan file di:  <root_app>/static/media_kamar/
# Format yang didukung:
#   Foto  → .jpg, .jpeg, .png, .webp, .gif
#   Video → .mp4, .webm, .mov
MEDIA_KAMAR_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'media_kamar'
)

FOTO_EXT  = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
VIDEO_EXT = {'.mp4', '.webm', '.mov'}


def _get_media_list():
    """Kembalikan list dict [{type, url, name}] dari folder media_kamar."""
    if not os.path.isdir(MEDIA_KAMAR_FOLDER):
        return []

    hasil = []
    for fname in sorted(os.listdir(MEDIA_KAMAR_FOLDER)):
        ext = os.path.splitext(fname)[1].lower()
        if ext in FOTO_EXT:
            hasil.append({'type': 'foto',  'url': f'/media-kamar/file/{fname}', 'name': fname})
        elif ext in VIDEO_EXT:
            hasil.append({'type': 'video', 'url': f'/media-kamar/file/{fname}', 'name': fname})

    return hasil


@media_kamar_bp.route('/media-kamar/list')
def list_media():
    """
    Endpoint JSON untuk galeri login.
    Response: { "files": [ {type, url, name}, ... ] }
    """
    return jsonify({'files': _get_media_list()})


@media_kamar_bp.route('/media-kamar/file/<path:filename>')
def serve_file(filename):
    """Serve file foto / video dari folder static/media_kamar/"""
    # Pastikan folder ada
    if not os.path.isdir(MEDIA_KAMAR_FOLDER):
        return jsonify({'error': 'Folder media_kamar tidak ditemukan'}), 404

    # Keamanan: tolak path traversal
    safe_name = os.path.basename(filename)
    return send_from_directory(MEDIA_KAMAR_FOLDER, safe_name)
