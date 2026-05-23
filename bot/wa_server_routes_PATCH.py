"""
routes/wa_server_routes_PATCH.py
─────────────────────────────────────────────────────────────────────────────
INI ADALAH CONTOH PATCH untuk wa_server_routes.py yang sudah ada.
Cari fungsi webhook / receive message di wa_server_routes.py Anda,
lalu tambahkan potongan kode di bawah ini.

CARA INTEGRASI:
1. Buka routes/wa_server_routes.py
2. Di bagian IMPORT, tambahkan:
       from utils.wa_chatbot_handler import handle_incoming_wa
3. Di dalam fungsi yang menerima pesan WA masuk (biasanya endpoint /wa/webhook
   atau /wa/receive), tambahkan blok auto-reply di bawah ini.

─────────────────────────────────────────────────────────────────────────────
CONTOH – jika wa_server_routes.py Anda kira-kira seperti ini:

    @wa_server_bp.route('/wa/receive', methods=['POST'])
    def wa_receive():
        data   = request.get_json()
        sender = data.get('from')   # "6281234567890@s.whatsapp.net" atau "6281234567890"
        text   = data.get('body') or data.get('message') or ''
        # ... simpan ke DB, dsb ...
        return jsonify({'status': 'ok'})

TAMBAHKAN blok berikut tepat setelah mendapatkan sender & text:

─────────────────────────────────────────────────────────────────────────────
"""

# ════════════════════════════════════════════════════════════════
# BLOK YANG DITAMBAHKAN KE wa_server_routes.py
# (Tempel setelah baris yang mengambil sender & text)
# ════════════════════════════════════════════════════════════════

PATCH_CODE = r"""
# ── Auto-reply chatbot ─────────────────────────────────────────
import threading
from utils.wa_chatbot_handler import handle_incoming_wa

def _auto_reply_task(sender_num: str, text: str):
    \"\"\"Jalankan di thread terpisah agar tidak blok webhook response.\"\"\"
    try:
        # Bersihkan nomor: ambil angka saja, buang @s.whatsapp.net dst
        clean_sender = sender_num.split('@')[0].strip()

        # Abaikan pesan dari diri sendiri / status WA
        if clean_sender in ('status', '') or 'broadcast' in clean_sender.lower():
            return

        # Minta balasan dari AI
        reply = handle_incoming_wa(clean_sender, text)
        if not reply:
            return

        # Kirim balasan melalui fungsi/API yang sudah ada di wa_server_routes
        # Ganti baris di bawah sesuai cara app Anda mengirim WA:
        #
        # Opsi A – jika ada fungsi send_wa_message(to, message):
        #   send_wa_message(clean_sender, reply)
        #
        # Opsi B – jika pakai requests ke WA server internal:
        #   import requests
        #   requests.post('http://localhost:3000/send',
        #       json={'to': clean_sender, 'message': reply}, timeout=10)
        #
        # Opsi C – jika pakai fungsi kirim_pesan_wa yang ada di kirim_wa_routes:
        from utils.kirim_wa import kirim_pesan_wa   # sesuaikan path
        kirim_pesan_wa(clean_sender, reply)

    except Exception as e:
        print(f"[AutoReply] Gagal: {e}")

# Jalankan di background thread
t = threading.Thread(target=_auto_reply_task, args=(sender, text), daemon=True)
t.start()
# ── End auto-reply chatbot ─────────────────────────────────────
"""


# ════════════════════════════════════════════════════════════════
# ALTERNATIF: Jika wa_server_routes.py pakai Baileys webhook
# yang mengirim event JSON seperti:
# { "event": "messages.upsert", "messages": [{ "key": {...}, "message": {...} }] }
# ════════════════════════════════════════════════════════════════

BAILEYS_WEBHOOK_PATCH = r"""
@wa_server_bp.route('/wa/webhook', methods=['POST'])
def wa_webhook():
    data  = request.get_json(silent=True) or {}
    event = data.get('event', '')

    if event == 'messages.upsert':
        for msg in data.get('messages', []):
            key     = msg.get('key', {})
            from_me = key.get('fromMe', False)
            if from_me:
                continue   # abaikan pesan dari diri sendiri

            sender = key.get('remoteJid', '').split('@')[0]
            # Ambil teks dari berbagai tipe pesan
            msg_content = msg.get('message', {})
            text = (
                msg_content.get('conversation') or
                (msg_content.get('extendedTextMessage') or {}).get('text') or
                ''
            ).strip()

            if not text:
                continue   # abaikan media / voice note

            # Auto-reply di background thread
            import threading
            from utils.wa_chatbot_handler import handle_incoming_wa

            def _reply(s=sender, t=text):
                reply = handle_incoming_wa(s, t)
                if reply:
                    # Ganti sesuai cara kirim di app Anda
                    try:
                        from utils.kirim_wa import kirim_pesan_wa
                        kirim_pesan_wa(s, reply)
                    except Exception as e:
                        print(f"[Webhook] Gagal kirim: {e}")

            threading.Thread(target=_reply, daemon=True).start()

    return jsonify({'status': 'ok'})
"""

# Cetak instruksi saat dijalankan langsung
if __name__ == '__main__':
    print("=" * 60)
    print("PATCH untuk wa_server_routes.py")
    print("=" * 60)
    print("\n📌 LANGKAH:")
    print("1. Buka routes/wa_server_routes.py")
    print("2. Tambahkan import: from utils.wa_chatbot_handler import handle_incoming_wa")
    print("3. Tempel PATCH_CODE di dalam endpoint penerima pesan WA")
    print("4. Sesuaikan cara pengiriman WA (lihat Opsi A/B/C di PATCH_CODE)")
    print("\n📌 ATAU gunakan BAILEYS_WEBHOOK_PATCH jika pakai Baileys event webhook")
    print("\nLihat file ini untuk detail lengkap.")
