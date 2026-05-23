"""
utils/wa_chatbot_handler.py
Handler auto-reply WhatsApp – TANPA AI, langsung dari database.
Dipanggil dari wa_server_routes.py ketika ada pesan WA masuk.

CARA PAKAI:
  from utils.wa_chatbot_handler import handle_incoming_wa
  reply = handle_incoming_wa(sender, message_text)
  # lalu kirim 'reply' ke sender via Baileys/wa_server
"""
import time
from datetime import datetime
from models.database import get_db

_wa_last_seen: dict = {}
_WA_SESSION_TIMEOUT = 3600  # hapus cache jika idle > 1 jam

ADMIN_NO = "08159959605"

MENU_UTAMA = f"""Halo kak! 👋 Selamat datang di *Kost Kami*.

Ketik angka untuk pilih menu:
1️⃣  Cek tagihan saya
2️⃣  Info kamar tersedia
3️⃣  Info pembayaran
4️⃣  Hubungi admin

Ketik *menu* kapan saja untuk kembali ke sini."""


# ── State sederhana per nomor (untuk multi-step) ──────────────────────────────
# Format: { "628xxx": {"step": "main" | "cek_tagihan_nama", ...} }
_wa_state: dict = {}


def handle_incoming_wa(sender: str, message_text: str) -> str:
    """
    Proses pesan WA masuk, kembalikan teks balasan.
    sender: nomor WA pengirim (contoh: "6281234567890")
    """
    message_text = message_text.strip()
    if not message_text:
        return ''

    _cleanup_old_sessions()
    _wa_last_seen[sender] = time.time()

    if sender not in _wa_state:
        _wa_state[sender] = {'step': 'main'}

    msg  = message_text.lower()
    state = _wa_state[sender]

    # Kata kunci reset ke menu
    if msg in ('menu', 'halo', 'hai', 'hi', 'hello', 'help', 'bantuan', '0'):
        _wa_state[sender] = {'step': 'main'}
        reply = MENU_UTAMA

    # ── Step: menu utama ──────────────────────────────────────────────────────
    elif state['step'] == 'main':
        reply = _handle_main_menu(sender, msg)

    # ── Step: cek tagihan – minta nama/kamar ─────────────────────────────────
    elif state['step'] == 'cek_tagihan_input':
        reply = _handle_cek_tagihan(sender, message_text)

    else:
        _wa_state[sender] = {'step': 'main'}
        reply = MENU_UTAMA

    _log_wa_chat(sender, message_text, reply)
    return reply


# ── Handler per menu ──────────────────────────────────────────────────────────

def _handle_main_menu(sender: str, msg: str) -> str:
    # Deteksi via nomor WA terdaftar dulu
    penghuni = _get_penghuni_by_phone(sender)

    if msg == '1' or any(k in msg for k in ('tagihan', 'bayar', 'cicil', 'tunggak', 'lunas')):
        if penghuni:
            # Langsung tampilkan tagihan miliknya
            reply = _info_tagihan_penghuni(penghuni['id'], penghuni['nama'])
        else:
            # Minta input nama/nomor kamar
            _wa_state[sender] = {'step': 'cek_tagihan_input'}
            reply = (
                "Silakan ketik *nama* atau *nomor kamar* kamu kak,\n"
                "contoh: _Budi_ atau _A1_\n\n"
                "_(Ketik *menu* untuk kembali)_"
            )

    elif msg == '2' or any(k in msg for k in ('kamar', 'kosong', 'tersedia', 'sewa', 'harga')):
        reply = _info_kamar_tersedia()

    elif msg == '3' or any(k in msg for k in ('pembayaran', 'transfer', 'rekening', 'cara bayar')):
        reply = _info_pembayaran()

    elif msg == '4' or any(k in msg for k in ('admin', 'hubungi', 'kontak', 'cs')):
        reply = _info_admin()

    else:
        reply = (
            f"Maaf kak, perintah tidak dikenali 🙏\n\n{MENU_UTAMA}"
        )

    return reply


def _handle_cek_tagihan(sender: str, input_text: str) -> str:
    """Cari penghuni berdasarkan nama atau nomor kamar yang diketik."""
    _wa_state[sender] = {'step': 'main'}  # reset state

    conn = get_db()
    # Coba cocokkan nomor kamar dulu
    row = conn.execute(
        "SELECT id, nama, nomor_kamar FROM penghuni WHERE LOWER(nomor_kamar)=? AND aktif=1",
        (input_text.lower(),)
    ).fetchone()

    # Jika tidak ketemu, coba cari nama (LIKE)
    if not row:
        row = conn.execute(
            "SELECT id, nama, nomor_kamar FROM penghuni WHERE LOWER(nama) LIKE ? AND aktif=1",
            (f'%{input_text.lower()}%',)
        ).fetchone()
    conn.close()

    if not row:
        return (
            f"❌ Penghuni dengan nama/kamar *{input_text}* tidak ditemukan.\n\n"
            f"Pastikan nama/nomor kamar sesuai, atau hubungi admin: {ADMIN_NO} 😊"
        )

    return _info_tagihan_penghuni(row['id'], row['nama'])


# ── Fungsi ambil data dari DB ─────────────────────────────────────────────────

def _info_tagihan_penghuni(penghuni_id: int, nama: str) -> str:
    conn = get_db()
    rows = conn.execute(
        """SELECT bulan, jumlah, status, tanggal_jatuh_tempo
           FROM tagihan
           WHERE penghuni_id = ?
           ORDER BY bulan DESC
           LIMIT 6""",
        (penghuni_id,)
    ).fetchall()
    conn.close()

    if not rows:
        return f"Halo kak *{nama}* 😊\nBelum ada data tagihan untuk akun kamu."

    lines = [f"📋 *Tagihan – {nama}*\n"]
    for r in rows:
        bulan_fmt = _format_bulan(r['bulan'])
        status_emoji = '✅' if r['status'] == 'lunas' else '⏳' if r['status'] == 'cicilan' else '❌'
        lines.append(
            f"{status_emoji} {bulan_fmt}: Rp {r['jumlah']:,.0f} – _{r['status']}_"
        )

    belum = [r for r in rows if r['status'] != 'lunas']
    if belum:
        total = sum(r['jumlah'] for r in belum)
        lines.append(f"\n💰 Total belum lunas: *Rp {total:,.0f}*")
        lines.append(f"📞 Hubungi admin untuk pembayaran: {ADMIN_NO}")
    else:
        lines.append("\n✅ Semua tagihan *lunas*. Terima kasih kak! 🙏")

    return '\n'.join(lines)


def _info_kamar_tersedia() -> str:
    conn = get_db()
    rows = conn.execute(
        "SELECT nomor_kamar, harga_sewa FROM penghuni WHERE aktif=0 ORDER BY nomor_kamar"
    ).fetchall()
    semua = conn.execute("SELECT COUNT(*) as total FROM penghuni").fetchone()
    terisi = conn.execute("SELECT COUNT(*) as total FROM penghuni WHERE aktif=1").fetchone()
    conn.close()

    lines = ["🏠 *Info Kamar Kost Kami*\n"]
    if rows:
        lines.append("*Kamar Tersedia:*")
        for r in rows:
            lines.append(f"  • Kamar {r['nomor_kamar']}: Rp {r['harga_sewa']:,.0f}/bulan")
    else:
        lines.append("😔 Saat ini semua kamar *penuh*.")

    lines.append(
        f"\nTotal kamar: {semua['total']} | "
        f"Terisi: {terisi['total']} | "
        f"Kosong: {semua['total'] - terisi['total']}"
    )
    lines.append(f"\n📞 Info & booking: {ADMIN_NO}")
    return '\n'.join(lines)


def _info_pembayaran() -> str:
    return (
        "💳 *Info Pembayaran*\n\n"
        "• Pembayaran via transfer bank atau tunai ke admin\n"
        "• Batas bayar: sesuai tanggal jatuh tempo\n"
        "• Setelah transfer, konfirmasi ke admin\n"
        f"• Kontak admin: {ADMIN_NO} (WA/telp)\n"
        "• Jam admin: 08.00 – 21.00 WIB\n\n"
        "_(Ketik *menu* untuk kembali)_"
    )


def _info_admin() -> str:
    return (
        f"📞 *Hubungi Admin Kost Kami*\n\n"
        f"WhatsApp / Telp: *{ADMIN_NO}*\n"
        f"Jam layanan: 08.00 – 21.00 WIB\n\n"
        f"Untuk keluhan, perbaikan, dan info lainnya silakan hubungi langsung ya kak 🙏"
    )


def _get_penghuni_by_phone(sender: str):
    """Cek apakah nomor WA pengirim adalah penghuni terdaftar."""
    try:
        conn  = get_db()
        suffix = sender[-9:]
        row = conn.execute(
            """SELECT id, nama, nomor_kamar, harga_sewa
               FROM penghuni
               WHERE REPLACE(REPLACE(REPLACE(no_hp,' ',''),'-',''),'+','') LIKE ?
               AND aktif = 1""",
            (f'%{suffix}',)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[WA Handler] Gagal cek penghuni: {e}")
        return None


# ── Helper ────────────────────────────────────────────────────────────────────

def _format_bulan(bulan_str: str) -> str:
    bulan_id = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
                'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
    try:
        y, m = bulan_str.split('-')
        return f"{bulan_id[int(m)]} {y}"
    except Exception:
        return bulan_str


def _log_wa_chat(sender: str, message: str, reply: str):
    """Catat percakapan WA ke database."""
    try:
        conn = get_db()
        suffix = sender[-9:]
        row = conn.execute(
            "SELECT id FROM penghuni WHERE REPLACE(REPLACE(no_hp,' ',''),'-','') LIKE ? AND aktif=1",
            (f'%{suffix}',)
        ).fetchone()
        penghuni_id = row['id'] if row else None
        conn.execute(
            """INSERT INTO notif_wa (penghuni_id, pesan, status, tanggal_kirim)
               VALUES (?, ?, 'chatbot', datetime('now','localtime'))""",
            (penghuni_id, f"[USER] {message}\n[BOT] {reply[:500]}")
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WA Handler] Gagal log: {e}")


def _cleanup_old_sessions():
    """Hapus state WA yang sudah tidak aktif > 1 jam."""
    now = time.time()
    expired = [num for num, ts in _wa_last_seen.items()
               if now - ts > _WA_SESSION_TIMEOUT]
    for num in expired:
        _wa_state.pop(num, None)
        _wa_last_seen.pop(num, None)


# ── Web widget handler (pakai session_id dari Flask) ──────────────────────────

MENU_WEB = """Halo kak! 👋 Selamat datang di <b>Kost Kami</b>.

Pilih menu:
<br>1️⃣ Cek tagihan
<br>2️⃣ Info kamar tersedia
<br>3️⃣ Info pembayaran
<br>4️⃣ Hubungi admin

<i>Ketik "menu" untuk kembali ke sini.</i>"""

_web_state: dict = {}
_web_last_seen: dict = {}


def handle_web_message(session_id: str, message_text: str) -> str:
    """
    Proses pesan dari widget web.
    session_id: IP atau Flask session ID pengguna.
    """
    message_text = message_text.strip()
    if not message_text:
        return ''

    _web_last_seen[session_id] = time.time()

    if session_id not in _web_state:
        _web_state[session_id] = {'step': 'main'}

    msg   = message_text.lower()
    state = _web_state[session_id]

    if msg in ('menu', 'halo', 'hai', 'hi', 'hello', 'help', '0', 'bantuan'):
        _web_state[session_id] = {'step': 'main'}
        return MENU_WEB

    if state['step'] == 'cek_tagihan_input':
        _web_state[session_id] = {'step': 'main'}
        return _handle_cek_tagihan_web(message_text)

    # Menu utama
    if msg == '1' or any(k in msg for k in ('tagihan', 'bayar', 'tunggak', 'lunas')):
        _web_state[session_id] = {'step': 'cek_tagihan_input'}
        return (
            "Silakan ketik <b>nama</b> atau <b>nomor kamar</b> kamu kak.<br>"
            "<i>(contoh: Budi atau A1)</i>"
        )
    elif msg == '2' or any(k in msg for k in ('kamar', 'kosong', 'tersedia', 'sewa', 'harga')):
        return _info_kamar_web()
    elif msg == '3' or any(k in msg for k in ('pembayaran', 'transfer', 'rekening', 'cara bayar')):
        return _info_pembayaran_web()
    elif msg == '4' or any(k in msg for k in ('admin', 'hubungi', 'kontak')):
        return _info_admin_web()
    else:
        return f"Maaf kak, tidak dikenali 🙏<br><br>{MENU_WEB}"


def _handle_cek_tagihan_web(input_text: str) -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT id, nama FROM penghuni WHERE LOWER(nomor_kamar)=? AND aktif=1",
        (input_text.lower(),)
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT id, nama FROM penghuni WHERE LOWER(nama) LIKE ? AND aktif=1",
            (f'%{input_text.lower()}%',)
        ).fetchone()
    conn.close()

    if not row:
        return (
            f"❌ Penghuni <b>{input_text}</b> tidak ditemukan.<br>"
            f"Hubungi admin: <b>{ADMIN_NO}</b>"
        )

    # Ambil tagihan
    conn = get_db()
    rows = conn.execute(
        "SELECT bulan, jumlah, status FROM tagihan WHERE penghuni_id=? ORDER BY bulan DESC LIMIT 6",
        (row['id'],)
    ).fetchall()
    conn.close()

    if not rows:
        return f"Halo kak <b>{row['nama']}</b> 😊<br>Belum ada data tagihan."

    lines = [f"📋 <b>Tagihan – {row['nama']}</b><br>"]
    for r in rows:
        bulan_fmt = _format_bulan(r['bulan'])
        icon = '✅' if r['status'] == 'lunas' else '❌'
        lines.append(f"{icon} {bulan_fmt}: Rp {r['jumlah']:,.0f} – <i>{r['status']}</i>")

    belum = [r for r in rows if r['status'] != 'lunas']
    if belum:
        total = sum(r['jumlah'] for r in belum)
        lines.append(f"<br>💰 Total belum lunas: <b>Rp {total:,.0f}</b>")
        lines.append(f"📞 Hubungi admin: {ADMIN_NO}")
    else:
        lines.append("<br>✅ Semua tagihan <b>lunas</b>. Terima kasih! 🙏")

    return '<br>'.join(lines)


def _info_kamar_web() -> str:
    conn = get_db()
    rows   = conn.execute("SELECT nomor_kamar, harga_sewa FROM penghuni WHERE aktif=0 ORDER BY nomor_kamar").fetchall()
    semua  = conn.execute("SELECT COUNT(*) as t FROM penghuni").fetchone()
    terisi = conn.execute("SELECT COUNT(*) as t FROM penghuni WHERE aktif=1").fetchone()
    conn.close()

    lines = ["🏠 <b>Info Kamar Kost Kami</b><br>"]
    if rows:
        lines.append("<b>Kamar Tersedia:</b>")
        for r in rows:
            lines.append(f"• Kamar {r['nomor_kamar']}: Rp {r['harga_sewa']:,.0f}/bulan")
    else:
        lines.append("😔 Semua kamar saat ini <b>penuh</b>.")

    kosong = semua['t'] - terisi['t']
    lines.append(f"<br>Total: {semua['t']} | Terisi: {terisi['t']} | Kosong: {kosong}")
    lines.append(f"📞 Info & booking: {ADMIN_NO}")
    return '<br>'.join(lines)


def _info_pembayaran_web() -> str:
    return (
        "💳 <b>Info Pembayaran</b><br><br>"
        "• Transfer bank atau tunai ke admin<br>"
        "• Batas bayar sesuai tanggal jatuh tempo<br>"
        "• Setelah transfer, konfirmasi ke admin<br>"
        f"• Kontak: <b>{ADMIN_NO}</b> (WA/telp)<br>"
        "• Jam admin: 08.00 – 21.00 WIB"
    )


def _info_admin_web() -> str:
    return (
        f"📞 <b>Hubungi Admin</b><br><br>"
        f"WA / Telp: <b>{ADMIN_NO}</b><br>"
        f"Jam: 08.00 – 21.00 WIB<br><br>"
        f"Silakan hubungi langsung ya kak 🙏"
    )
