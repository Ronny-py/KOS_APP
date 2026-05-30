"""
routes/media_fasilitas_routes.py
Melayani foto & video fasilitas dari folder static/media_fasilitas/
"""
import os
from flask import Blueprint, jsonify, send_from_directory

media_fasilitas_bp = Blueprint('media_fasilitas', __name__)

MEDIA_FASILITAS_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'media_fasilitas'
)
FOTO_EXT  = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
VIDEO_EXT = {'.mp4', '.webm', '.mov'}


def _get_media_list():
    if not os.path.isdir(MEDIA_FASILITAS_FOLDER):
        return []
    hasil = []
    for fname in sorted(os.listdir(MEDIA_FASILITAS_FOLDER)):
        ext = os.path.splitext(fname)[1].lower()
        if ext in FOTO_EXT:
            hasil.append({'type': 'foto',  'url': f'/media-fasilitas/file/{fname}', 'name': fname})
        elif ext in VIDEO_EXT:
            hasil.append({'type': 'video', 'url': f'/media-fasilitas/file/{fname}', 'name': fname})
    return hasil


@media_fasilitas_bp.route('/media-fasilitas/list')
def list_media():
    return jsonify({'files': _get_media_list()})


@media_fasilitas_bp.route('/media-fasilitas/file/<path:filename>')
def serve_file(filename):
    if not os.path.isdir(MEDIA_FASILITAS_FOLDER):
        return jsonify({'error': 'Folder tidak ditemukan'}), 404
    safe_name = os.path.basename(filename)
    return send_from_directory(MEDIA_FASILITAS_FOLDER, safe_name)
