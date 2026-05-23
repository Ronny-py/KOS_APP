"""
SETUP WHATSAPP.JS INTEGRATION
=============================

Panduan setup untuk integrasi WhatsApp.js dengan Flask app.

1. INSTALL WHATSAPP.JS SERVER
=============================

Pastikan Anda sudah install Node.js dan npm.

# Clone atau install WhatsApp.js
npm install whatsapp-web.js

# Atau gunakan WhatsApp.js server yang sudah jadi:
npm install wa-web-api
npm install express body-parser cors

2. BUAT WHATSAPP.JS SERVER
===========================

Buat file: wa-server/server.js

```javascript
const express = require('express');
const { Client } = require('whatsapp-web.js');
const qrcode = require('qr-code');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const client = new Client({
    puppeteer: {
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    }
});

let isReady = false;

// QR Code untuk login WhatsApp
client.on('qr', (qr) => {
    console.log('QR CODE:', qr);
    // Scan dengan WhatsApp di HP Anda
});

client.on('ready', () => {
    console.log('✅ WhatsApp.js ready!');
    isReady = true;
});

client.on('authenticated', () => {
    console.log('✅ WhatsApp authenticated!');
});

client.initialize();

// API: Send message
app.post('/api/send-message', async (req, res) => {
    try {
        const { number, message, instance } = req.body;
        
        if (!isReady) {
            return res.status(503).json({
                success: false,
                message: 'WhatsApp client not ready'
            });
        }
        
        // Format: +62812345678
        const chatId = number + '@c.us';
        
        await client.sendMessage(chatId, message);
        
        res.json({
            success: true,
            message: 'Message sent',
            number: number
        });
    } catch (error) {
        console.error('Send error:', error);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// API: Health check
app.get('/api/health', (req, res) => {
    res.json({
        status: isReady ? 'ready' : 'initializing',
        message: 'WhatsApp.js server is running'
    });
});

// API: Get status
app.get('/api/status', (req, res) => {
    res.json({
        ready: isReady,
        message: isReady ? 'Ready to send messages' : 'Waiting for QR scan'
    });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`WhatsApp.js server running on port ${PORT}`);
});
```

3. INSTALL DEPENDENCIES
=======================

Di folder wa-server/:

npm install express body-parser cors whatsapp-web.js qr-code puppeteer

4. JALANKAN SERVER
==================

node wa-server/server.js

Scan QR code dengan WhatsApp di HP Anda untuk login.

5. KONFIGURASI DI FLASK APP
============================

Edit file: utils/wa_service.py

Ubah konfigurasi:

WHATSAPP_SERVER_URL = "http://localhost:3000"  # Sesuai IP dan port
WHATSAPP_API_KEY = None  # Jika tidak pakai auth
WHATSAPP_INSTANCE_ID = "default"

Atau set via environment variables di .env:

WHATSAPP_SERVER_URL=http://localhost:3000
WHATSAPP_API_KEY=your-api-key
WHATSAPP_INSTANCE_ID=default

6. TESTING
==========

Test dari Flask:

from utils.wa_service import kirim_wa, check_wa_server

# Check server status
health = check_wa_server()
print(health)

# Kirim pesan
sukses, error = kirim_wa("081234567890", "Halo ini test")
if sukses:
    print("✅ Pesan terkirim!")
else:
    print(f"❌ Error: {error}")

7. TROUBLESHOOTING
==================

❌ "WhatsApp.js server tidak terhubung"
→ Pastikan wa-server sudah running: node wa-server/server.js

❌ "Timeout"
→ Server lambat merespons, cek internet dan hardware

❌ "Invalid message format"
→ Nomor HP harus format +62xxx

❌ "Client not ready"
→ Belum scan QR code, tunggu sampai "✅ WhatsApp.js ready!"

8. MONITORING LOG
=================

Lihat history pengiriman di:
- Database table: notif_wa
- Routes: /notif-wa/
- API: /notif-wa/api/stats

9. SECURITY NOTES
=================

- Jangan share API key di public repo
- Use environment variables untuk config
- Add API authentication ke WhatsApp.js server
- Monitor penggunaan untuk prevent abuse

10. MULTIPLE INSTANCES (OPSIONAL)
=================================

Jika perlu multiple WhatsApp account:

Modifikasi wa-server/server.js untuk support multiple client instances.

Atau gunakan load balancer untuk multiple server di port berbeda.

===========================================
Setup selesai! Sekarang Anda bisa mengirim
pesan WhatsApp dari Flask app.
===========================================
"""
