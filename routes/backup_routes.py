"""
routes/backup_routes.py
Menu Backup & Restore Database KostPay
- Backup ke file lokal (.db + .sql)
- Backup ke Google Drive (OAuth2)
- Restore dari file upload
- Restore dari Google Drive
"""

import os
import shutil
import sqlite3
import json
import io
import re
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, send_file, jsonify, current_app
)
from config import DATABASE

backup_bp = Blueprint('backup', __name__, url_prefix='/backup')

# ── Folder penyimpanan backup lokal ──────────────────────────────────────────
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backups')

# ── Google OAuth2 scope ───────────────────────────────────────────────────────
GDRIVE_SCOPES  = ['https://www.googleapis.com/auth/drive.file']
GDRIVE_TOKEN   = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gdrive_token.json')
GDRIVE_CREDS   = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gdrive_credentials.json')
GDRIVE_FOLDER  = 'KostPay Backup'   # nama folder di Google Drive


def _require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _db_path():
    return DATABASE


def _timestamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


# ── Backup helpers ─────────────────────────────────────────────────────────────

def _backup_as_db(dest_path: str):
    """Salin file .db langsung (binary copy)."""
    shutil.copy2(_db_path(), dest_path)


def _backup_as_sql(dest_path: str):
    """Dump seluruh isi database ke SQL dump."""
    conn = sqlite3.connect(_db_path())
    with open(dest_path, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(line + '\n')
    conn.close()


def _list_local_backups():
    _ensure_backup_dir()
    files = []
    for fn in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if fn.endswith(('.db', '.sql')):
            fp = os.path.join(BACKUP_DIR, fn)
            stat = os.stat(fp)
            files.append({
                'name':    fn,
                'size':    stat.st_size,
                'created': datetime.fromtimestamp(stat.st_mtime).strftime('%d %b %Y %H:%M:%S'),
            })
    return files


# ── Google Drive helpers ───────────────────────────────────────────────────────

def _gdrive_service():
    """Buat Google Drive service dari token yang tersimpan."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    if not os.path.exists(GDRIVE_TOKEN):
        return None
    creds = Credentials.from_authorized_user_file(GDRIVE_TOKEN, GDRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            with open(GDRIVE_TOKEN, 'w') as f:
                f.write(creds.to_json())
        else:
            return None
    return build('drive', 'v3', credentials=creds)


def _gdrive_folder_id(service):
    """Ambil atau buat folder KostPay Backup di Google Drive."""
    res = service.files().list(
        q=f"name='{GDRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive', fields='files(id,name)'
    ).execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    # Buat folder baru
    meta = {'name': GDRIVE_FOLDER, 'mimeType': 'application/vnd.google-apps.folder'}
    folder = service.files().create(body=meta, fields='id').execute()
    return folder['id']


def _gdrive_list_backups(service):
    folder_id = _gdrive_folder_id(service)
    res = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        orderBy='createdTime desc',
        fields='files(id,name,size,createdTime)',
        pageSize=50
    ).execute()
    return res.get('files', [])


def _gdrive_upload(service, local_path: str, filename: str):
    from googleapiclient.http import MediaFileUpload
    folder_id = _gdrive_folder_id(service)
    mime = 'application/octet-stream' if filename.endswith('.db') else 'text/plain'
    meta = {'name': filename, 'parents': [folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
    service.files().create(body=meta, media_body=media, fields='id').execute()


def _gdrive_download(service, file_id: str, dest_path: str):
    from googleapiclient.http import MediaIoBaseDownload
    req = service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()


# ── Restore helpers ────────────────────────────────────────────────────────────

def _restore_from_db(source_path: str):
    """Restore langsung dari file .db."""
    db = _db_path()
    backup_current = db + '.pre_restore'
    shutil.copy2(db, backup_current)   # backup sebelum restore
    try:
        shutil.copy2(source_path, db)
    except Exception as e:
        shutil.copy2(backup_current, db)
        raise e


def _restore_from_sql(source_path: str):
    """Restore dari SQL dump."""
    db = _db_path()
    backup_current = db + '.pre_restore'
    shutil.copy2(db, backup_current)
    try:
        # Drop semua tabel lama lalu eksekusi dump
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        # Hapus semua tabel
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cur.fetchall()
        conn.execute("PRAGMA foreign_keys = OFF")
        for (tbl,) in tables:
            cur.execute(f"DROP TABLE IF EXISTS [{tbl}]")
        conn.commit()
        # Eksekusi SQL dump
        with open(source_path, 'r', encoding='utf-8') as f:
            sql = f.read()
        conn.executescript(sql)
        conn.commit()
        conn.close()
    except Exception as e:
        shutil.copy2(backup_current, db)
        raise e


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@backup_bp.route('/')
@_require_login
def index():
    local_files  = _list_local_backups()
    gdrive_auth  = os.path.exists(GDRIVE_TOKEN)
    gdrive_creds = os.path.exists(GDRIVE_CREDS)
    gdrive_files = []

    if gdrive_auth:
        try:
            svc = _gdrive_service()
            if svc:
                gdrive_files = _gdrive_list_backups(svc)
        except Exception as e:
            flash(f'Gagal ambil daftar Google Drive: {e}', 'warning')

    return render_template(
        'backup/index.html',
        local_files  = local_files,
        gdrive_auth  = gdrive_auth,
        gdrive_creds = gdrive_creds,
        gdrive_files = gdrive_files,
    )


# ── Backup lokal ──────────────────────────────────────────────────────────────

@backup_bp.route('/local/db', methods=['POST'])
@_require_login
def backup_local_db():
    _ensure_backup_dir()
    filename = f"kostpay_backup_{_timestamp()}.db"
    dest = os.path.join(BACKUP_DIR, filename)
    try:
        _backup_as_db(dest)
        flash(f'✅ Backup berhasil: {filename}', 'success')
    except Exception as e:
        flash(f'❌ Backup gagal: {e}', 'danger')
    return redirect(url_for('backup.index'))


@backup_bp.route('/local/sql', methods=['POST'])
@_require_login
def backup_local_sql():
    _ensure_backup_dir()
    filename = f"kostpay_backup_{_timestamp()}.sql"
    dest = os.path.join(BACKUP_DIR, filename)
    try:
        _backup_as_sql(dest)
        flash(f'✅ Backup SQL berhasil: {filename}', 'success')
    except Exception as e:
        flash(f'❌ Backup SQL gagal: {e}', 'danger')
    return redirect(url_for('backup.index'))


@backup_bp.route('/local/download/<filename>')
@_require_login
def download_backup(filename):
    # Sanitasi nama file
    filename = os.path.basename(filename)
    fp = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(fp):
        flash('File tidak ditemukan.', 'danger')
        return redirect(url_for('backup.index'))
    return send_file(fp, as_attachment=True, download_name=filename)


@backup_bp.route('/local/delete/<filename>', methods=['POST'])
@_require_login
def delete_local_backup(filename):
    filename = os.path.basename(filename)
    fp = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(fp):
        os.remove(fp)
        flash(f'🗑️ File {filename} dihapus.', 'info')
    else:
        flash('File tidak ditemukan.', 'danger')
    return redirect(url_for('backup.index'))


# ── Restore dari file upload ──────────────────────────────────────────────────

@backup_bp.route('/restore/upload', methods=['POST'])
@_require_login
def restore_upload():
    f = request.files.get('backup_file')
    if not f or f.filename == '':
        flash('Pilih file backup terlebih dahulu.', 'danger')
        return redirect(url_for('backup.index'))

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.db', '.sql'):
        flash('Format file tidak valid. Gunakan .db atau .sql', 'danger')
        return redirect(url_for('backup.index'))

    # Simpan sementara
    tmp = os.path.join(BACKUP_DIR, f'tmp_restore_{_timestamp()}{ext}')
    _ensure_backup_dir()
    f.save(tmp)

    try:
        if ext == '.db':
            _restore_from_db(tmp)
        else:
            _restore_from_sql(tmp)
        flash('✅ Restore berhasil! Database telah dipulihkan.', 'success')
    except Exception as e:
        flash(f'❌ Restore gagal: {e}', 'danger')
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    return redirect(url_for('backup.index'))


# ── Google Drive: OAuth ────────────────────────────────────────────────────────

@backup_bp.route('/gdrive/auth')
@_require_login
def gdrive_auth():
    if not os.path.exists(GDRIVE_CREDS):
        flash('File credentials.json Google belum dikonfigurasi. Upload dulu di Pengaturan.', 'danger')
        return redirect(url_for('backup.index'))
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        GDRIVE_CREDS,
        scopes=GDRIVE_SCOPES,
        redirect_uri=url_for('backup.gdrive_callback', _external=True)
    )
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['gdrive_state'] = state
    return redirect(auth_url)


@backup_bp.route('/gdrive/callback')
@_require_login
def gdrive_callback():
    from google_auth_oauthlib.flow import Flow
    state = session.get('gdrive_state', '')
    flow = Flow.from_client_secrets_file(
        GDRIVE_CREDS,
        scopes=GDRIVE_SCOPES,
        state=state,
        redirect_uri=url_for('backup.gdrive_callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    with open(GDRIVE_TOKEN, 'w') as f:
        f.write(creds.to_json())
    flash('✅ Akun Google Drive berhasil terhubung!', 'success')
    return redirect(url_for('backup.index'))


@backup_bp.route('/gdrive/disconnect', methods=['POST'])
@_require_login
def gdrive_disconnect():
    if os.path.exists(GDRIVE_TOKEN):
        os.remove(GDRIVE_TOKEN)
        flash('🔌 Google Drive diputus.', 'info')
    return redirect(url_for('backup.index'))


@backup_bp.route('/gdrive/upload-creds', methods=['POST'])
@_require_login
def gdrive_upload_creds():
    """Upload file credentials.json dari Google Cloud Console."""
    f = request.files.get('creds_file')
    if not f or f.filename == '':
        flash('Pilih file credentials.json.', 'danger')
        return redirect(url_for('backup.index'))
    try:
        data = json.loads(f.read().decode('utf-8'))
        # Validasi minimal
        if 'web' not in data and 'installed' not in data:
            raise ValueError('File bukan credentials OAuth2 yang valid.')
        with open(GDRIVE_CREDS, 'w') as out:
            json.dump(data, out)
        flash('✅ Credentials berhasil diupload. Silakan hubungkan akun Google.', 'success')
    except Exception as e:
        flash(f'❌ File tidak valid: {e}', 'danger')
    return redirect(url_for('backup.index'))


# ── Google Drive: Backup ───────────────────────────────────────────────────────

@backup_bp.route('/gdrive/backup/db', methods=['POST'])
@_require_login
def gdrive_backup_db():
    svc = _gdrive_service()
    if not svc:
        flash('Hubungkan Google Drive terlebih dahulu.', 'danger')
        return redirect(url_for('backup.index'))
    _ensure_backup_dir()
    filename = f"kostpay_backup_{_timestamp()}.db"
    tmp = os.path.join(BACKUP_DIR, filename)
    try:
        _backup_as_db(tmp)
        _gdrive_upload(svc, tmp, filename)
        flash(f'✅ Backup ke Google Drive berhasil: {filename}', 'success')
    except Exception as e:
        flash(f'❌ Backup Google Drive gagal: {e}', 'danger')
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return redirect(url_for('backup.index'))


@backup_bp.route('/gdrive/backup/sql', methods=['POST'])
@_require_login
def gdrive_backup_sql():
    svc = _gdrive_service()
    if not svc:
        flash('Hubungkan Google Drive terlebih dahulu.', 'danger')
        return redirect(url_for('backup.index'))
    _ensure_backup_dir()
    filename = f"kostpay_backup_{_timestamp()}.sql"
    tmp = os.path.join(BACKUP_DIR, filename)
    try:
        _backup_as_sql(tmp)
        _gdrive_upload(svc, tmp, filename)
        flash(f'✅ Backup SQL ke Google Drive berhasil: {filename}', 'success')
    except Exception as e:
        flash(f'❌ Backup SQL Google Drive gagal: {e}', 'danger')
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return redirect(url_for('backup.index'))


# ── Google Drive: Restore ──────────────────────────────────────────────────────

@backup_bp.route('/gdrive/restore/<file_id>', methods=['POST'])
@_require_login
def gdrive_restore(file_id):
    svc = _gdrive_service()
    if not svc:
        flash('Hubungkan Google Drive terlebih dahulu.', 'danger')
        return redirect(url_for('backup.index'))

    # Ambil metadata nama file
    try:
        meta = svc.files().get(fileId=file_id, fields='name').execute()
        filename = meta.get('name', 'restore_tmp')
    except Exception:
        filename = 'restore_tmp.db'

    ext = os.path.splitext(filename)[1].lower()
    _ensure_backup_dir()
    tmp = os.path.join(BACKUP_DIR, f'gdrive_restore_{_timestamp()}{ext}')

    try:
        _gdrive_download(svc, file_id, tmp)
        if ext == '.db':
            _restore_from_db(tmp)
        else:
            _restore_from_sql(tmp)
        flash(f'✅ Restore dari Google Drive ({filename}) berhasil!', 'success')
    except Exception as e:
        flash(f'❌ Restore dari Google Drive gagal: {e}', 'danger')
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    return redirect(url_for('backup.index'))


@backup_bp.route('/gdrive/delete/<file_id>', methods=['POST'])
@_require_login
def gdrive_delete(file_id):
    svc = _gdrive_service()
    if not svc:
        flash('Hubungkan Google Drive terlebih dahulu.', 'danger')
        return redirect(url_for('backup.index'))
    try:
        svc.files().delete(fileId=file_id).execute()
        flash('🗑️ File di Google Drive dihapus.', 'info')
    except Exception as e:
        flash(f'❌ Gagal hapus: {e}', 'danger')
    return redirect(url_for('backup.index'))
