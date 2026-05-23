"""
utils/license_guard.py

Validasi expiry admin tanpa server eksternal.
Proteksi berlapis:
  1. HMAC signature  → expired_at di DB tidak bisa diedit manual tanpa tahu SECRET
  2. last_seen check → deteksi jam sistem dimundurkan antar sesi
  3. max_date_seen   → deteksi rollback tanggal (monotonic counter)

Kode aktivasi format: GANGJANGKUNG + (tanggal_aktivasi + 31 hari)
Contoh: aktivasi 20260611 → GANGJANGKUNG20260712
"""
import hmac
import hashlib
from datetime import datetime, date, timedelta

# ── Ambil SECRET dari config ───────────────────────────────────────────────────
try:
    from config import SECRET_KEY as _SECRET
except ImportError:
    _SECRET = "kost-secret-2024-ganti-ini"

_HMAC_SALT = "license_guard_v1:"


def _sign(admin_id: int, expired_at_str: str) -> str:
    payload = f"{_HMAC_SALT}{admin_id}:{expired_at_str}"
    return hmac.new(
        _SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


# ── Public API ─────────────────────────────────────────────────────────────────

def buat_kode_aktivasi(tgl_aktivasi: date) -> str:
    """
    Generate kode aktivasi = GANGJANGKUNG + (tgl_aktivasi + 31 hari) format YYYYMMDD.
    Contoh: aktivasi 2026-06-11 → GANGJANGKUNG20260712
    """
    tgl_kode = tgl_aktivasi + timedelta(days=31)
    return f"GANGJANGKUNG{tgl_kode.strftime('%Y%m%d')}"


def verifikasi_kode_aktivasi(kode: str, tgl_aktivasi: date) -> bool:
    """Verifikasi kode yang diinput user cocok dengan tanggal aktivasi di DB."""
    return kode.strip() == buat_kode_aktivasi(tgl_aktivasi)


def buat_token(admin_id: int, expired_at_str: str) -> str:
    """Generate HMAC token untuk expired_at. Simpan di kolom expiry_token."""
    return _sign(admin_id, expired_at_str)


def validasi_expiry(admin: dict) -> tuple[bool, str]:
    """
    Validasi apakah admin boleh login.
    Return: (True, "OK") atau (False, "pesan error")
    """
    now   = datetime.now()
    today = now.date()

    admin_id      = admin.get("id")
    expired_at    = admin.get("expired_at") or ""
    last_seen     = admin.get("last_seen") or ""
    max_date_seen = admin.get("max_date_seen") or ""
    expiry_token  = admin.get("expiry_token") or ""

    # ── 1. Cek HMAC token ────────────────────────────────────────────────────
    if not expired_at:
        return False, "Akun belum memiliki tanggal kadaluarsa. Hubungi developer."

    expected_token = _sign(admin_id, expired_at)
    if expiry_token and not hmac.compare_digest(expiry_token, expected_token):
        return False, "Data lisensi tidak valid. Hubungi developer."

    # ── 2. Cek rollback jam (last_seen) ──────────────────────────────────────
    if last_seen:
        try:
            ls_dt = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
            if now < ls_dt:
                return False, (
                    f"Waktu sistem tidak valid (jam dimundurkan). "
                    f"Login terakhir: {last_seen}."
                )
        except ValueError:
            pass

    # ── 3. Cek rollback tanggal (max_date_seen) ───────────────────────────────
    if max_date_seen:
        try:
            max_dt = date.fromisoformat(max_date_seen)
            if today < max_dt:
                return False, (
                    f"Tanggal sistem tidak valid (dimundurkan dari {max_date_seen}). "
                    f"Hubungi developer."
                )
        except ValueError:
            pass

    # ── 4. Cek expired_at ────────────────────────────────────────────────────
    try:
        exp_date = date.fromisoformat(expired_at[:10])
    except ValueError:
        return False, "Format tanggal kadaluarsa tidak valid."

    if today > exp_date:
        return False, f"Lisensi kadaluarsa sejak {expired_at[:10]}. Hubungi developer."

    return True, "OK"


def update_timestamps(db, admin_id: int):
    """Update last_seen dan max_date_seen setelah login sukses."""
    now     = datetime.now()
    today   = now.date().isoformat()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        UPDATE admin
        SET last_seen = ?,
            max_date_seen = CASE
                WHEN max_date_seen IS NULL OR max_date_seen < ? THEN ?
                ELSE max_date_seen
            END
        WHERE id = ?
    """, (now_str, today, today, admin_id))
    db.commit()
