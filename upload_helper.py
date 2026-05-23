"""
utils/upload_helper.py
Helper untuk upload dan validasi file bukti transfer.
"""
import os
import uuid
from werkzeug.utils import secure_filename
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS


def allowed_file(filename: str) -> bool:
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_upload(file_obj) -> str | None:
    """
    Simpan file upload ke UPLOAD_FOLDER.
    Return: nama file yang disimpan, atau None jika gagal.
    """
    if not file_obj or file_obj.filename == '':
        return None
    if not allowed_file(file_obj.filename):
        return None

    ext = file_obj.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_obj.save(save_path)
    return unique_name


def delete_file(filename: str):
    """Hapus file dari UPLOAD_FOLDER."""
    if not filename:
        return
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)
