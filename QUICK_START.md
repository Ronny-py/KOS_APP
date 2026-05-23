╔════════════════════════════════════════════════════════════════════════════════╗
║                  QUICK START: WhatsApp.js Server                              ║
╚════════════════════════════════════════════════════════════════════════════════╝

📋 REQUIREMENT:
===============
✅ Node.js 14+ (download: https://nodejs.org/)
✅ npm (biasanya include dengan Node.js)
✅ HP dengan WhatsApp (untuk scan QR code)


🚀 LANGKAH 1: Persiapan Folder
================================

1. Buat folder baru untuk WhatsApp.js server:
   
   mkdir wa-server
   cd wa-server

2. Copy file ini ke folder wa-server:
   - server.js
   - package.json
   - .env.example


🛠️  LANGKAH 2: Install Dependencies
=====================================

Jalankan command di folder wa-server:

   npm install

Tunggu sampai selesai (± 2-5 menit), tergantung internet.
Anda akan melihat folder "node_modules" dibuat.


⚙️  LANGKAH 3: Konfigurasi (Opsional)
=====================================

1. Buat file .env di folder wa-server (copy dari .env.example):
   
   cp .env.example .env

2. Edit .env jika perlu:
   
   PORT=3000
   API_KEY=your-api-key-here


🎯 LANGKAH 4: Jalankan Server
==============================

Di folder wa-server, jalankan:

   npm start

Atau gunakan nodemon untuk auto-reload (development):

   npm run dev


✅ LANGKAH 5: Scan QR Code
===========================

1. Tunggu terminal menampilkan QR CODE
   
   Anda akan lihat:
   📱 QR CODE MUNCUL - SCAN DENGAN WHATSAPP DI HP ANDA:
   [QR CODE di sini]

2. Buka WhatsApp di HP Anda
   
   - Buka Settings → Linked Devices
   - Klik "Link a device"
   - Scan QR code di terminal

3. Tunggu sampai muncul:
   
   ✅ WhatsApp client ready!
   ✅ WhatsApp authenticated!

SELESAI! Server sudah siap digunakan.


🧪 LANGKAH 6: Test Server
===========================

Opsi A: Buka browser
-----------
1. Buka: http://localhost:3000
2. Masukkan nomor HP: +62812345678
3. Klik "Send"
4. Lihat hasilnya

Opsi B: Dari terminal
-----------
curl -X POST http://localhost:3000/api/send-message \
  -H "Content-Type: application/json" \
  -d '{
    "number": "+62812345678",
    "message": "Halo, ini test message"
  }'

Opsi C: Dari Python
-----------
import requests

response = requests.post(
    'http://localhost:3000/api/send-message',
    json={
        'number': '+62812345678',
        'message': 'Halo, ini test message'
    }
)

print(response.json())


🔗 LANGKAH 7: Hubungkan dengan Flask App
=========================================

1. Pastikan wa_service.py di Flask app punya config:
   
   WHATSAPP_SERVER_URL = "http://localhost:3000"

2. Test dari Flask:
   
   from utils.wa_service import check_wa_server
   print(check_wa_server())

3. Coba kirim pesan dari aplikasi


📊 API ENDPOINTS
=================

GET /api/health
  → Check if server is running

GET /api/status
  → Check if WhatsApp ready to send

POST /api/send-message
  → Send text message
  Body: { "number": "+62812xxx", "message": "..." }

POST /api/send-message-with-media
  → Send message with image/file
  Body: { "number": "+62812xxx", "message": "...", "mediaUrl": "..." }

GET /api/chats
  → Get list of chats

POST /api/logout
  → Logout dan reset (perlu scan QR lagi)


⚠️  TROUBLESHOOTING
===================

❌ "Cannot find module 'whatsapp-web.js'"
→ Jalankan: npm install

❌ "Port 3000 already in use"
→ Ganti PORT di .env atau kill process yang pakai port 3000
→ Atau jalankan di port lain: PORT=3001 npm start

❌ "QR Code tidak muncul"
→ Pastikan terminal bisa menampilkan output
→ Coba terminal yang berbeda (cmd, PowerShell, atau bash)

❌ "WhatsApp.js server tidak terhubung"
→ Pastikan server sudah running: npm start
→ Cek firewall/antivirus tidak block port 3000
→ Cek browser bisa akses http://localhost:3000

❌ "Pesan tidak terkirim"
→ Pastikan HP sudah scan QR dan authenticated
→ Pastikan nomor HP format benar: +62812xxx
→ Cek WhatsApp aktif di HP dan tidak kadaluarsa

❌ Server crash/disconnect
→ Lihat error message di terminal
→ Restart server: npm start


🔒 SECURITY TIPS
=================

1. Set API_KEY di .env jika production:
   API_KEY=something-very-secret

2. Jangan commit .env ke git
   Tambahkan ke .gitignore:
   node_modules/
   .env

3. Gunakan HTTPS jika production (setup nginx/reverse proxy)

4. Monitor rate limit dari WhatsApp


📝 NOTES
========

- Server akan menyimpan session di folder ".wwebjs_auth"
- Jangan hapus folder ini kecuali mau logout
- WhatsApp.js tidak official, bisa berubah kapan saja
- Batasi pengiriman pesan untuk avoid blocked oleh WhatsApp


🆘 BANTUAN LEBIH LANJUT
========================

Jika ada error, lihat:
1. Console output dari npm start
2. Log di /logs folder (jika ada)
3. Issue di GitHub whatsapp-web.js

Dokumentasi: https://docs.wwebjs.dev/

═══════════════════════════════════════════════════════════════════════════════

👉 LANGKAH BERIKUTNYA:

1. Setup folder dan install: npm install
2. Jalankan server: npm start
3. Scan QR code dengan WhatsApp
4. Coba test kirim pesan
5. Hubungkan dengan Flask app

GOOD LUCK! 🚀
