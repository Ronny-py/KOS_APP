/**
 * WhatsApp.js Server
 * Mengirim pesan WhatsApp dari Flask app
 * 
 * Jalankan dengan: node server.js
 */

const express = require('express');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const cors = require('cors');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// ─── Konfigurasi ────────────────────────────────────────────────────────────

const PORT = process.env.PORT || 3000;
const API_KEY = process.env.API_KEY || null;  // Set di .env jika perlu security

let client = null;
let isReady = false;

// ─── Initialize WhatsApp Client ─────────────────────────────────────────────

const initWhatsApp = () => {
  client = new Client({
    authStrategy: new LocalAuth({
      clientId: 'default'
    }),
    puppeteer: {
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage'
      ]
    }
  });

  // Event: QR Code untuk scan
  client.on('qr', (qr) => {
    console.log('\n📱 QR CODE MUNCUL - SCAN DENGAN WHATSAPP DI HP ANDA:\n');
    qrcode.generate(qr, { small: true });
    console.log('\n');
  });

  // Event: Ready
  client.on('ready', () => {
    console.log('✅ WhatsApp client ready!');
    isReady = true;
  });

  // Event: Authenticated
  client.on('authenticated', () => {
    console.log('✅ WhatsApp authenticated!');
  });

  // Event: Auth failure
  client.on('auth_failure', (msg) => {
    console.error('❌ Auth failure:', msg);
    isReady = false;
  });

  // Event: Disconnected
  client.on('disconnected', (reason) => {
    console.log('❌ Client disconnected:', reason);
    isReady = false;
  });

  // Event: Message – auto-reply via Flask
  client.on('message', async (message) => {
    // Abaikan pesan dari grup dan pesan status
    if (message.from.includes('@g.us') || message.from === 'status@broadcast') return;

    const sender  = message.from.replace('@c.us', '');
    const msgBody = message.body;
    console.log(`📨 Message from ${sender}: ${msgBody}`);

    try {
      const res = await fetch('http://localhost:5000/api/chatbot/wa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from: sender, message: msgBody })
      });
      const data = await res.json();
      if (data.reply) {
        await message.reply(data.reply);
        console.log(`✅ Auto-reply sent to ${sender}`);
      }
    } catch (err) {
      console.error('❌ Auto-reply error:', err.message);
    }
  });

  // Initialize
  client.initialize();
};

// Initialize on startup
initWhatsApp();

// ─── Middleware: API Key Validation ──────────────────────────────────────────

const validateApiKey = (req, res, next) => {
  if (API_KEY && API_KEY !== 'your-api-key-here') {
    const auth = req.headers.authorization;
    if (!auth || !auth.startsWith('Bearer ')) {
      return res.status(401).json({
        success: false,
        message: 'Missing or invalid API key'
      });
    }
    
    const token = auth.split(' ')[1];
    if (token !== API_KEY) {
      return res.status(403).json({
        success: false,
        message: 'Invalid API key'
      });
    }
  }
  next();
};

// ─── Routes ─────────────────────────────────────────────────────────────────

// API: Health check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'WhatsApp.js server is running',
    ready: isReady,
    timestamp: new Date().toISOString()
  });
});

// API: Status server
app.get('/api/status', (req, res) => {
  res.json({
    ready: isReady,
    message: isReady ? '✅ Ready to send messages' : '⏳ Waiting for QR scan',
    timestamp: new Date().toISOString()
  });
});

// API: Send message
app.post('/api/send-message', validateApiKey, async (req, res) => {
  try {
    const { number, message, mediaUrl, instance } = req.body;

    // Validasi input
    if (!number || !message) {
      return res.status(400).json({
        success: false,
        message: 'number dan message harus diisi'
      });
    }

    // Check client ready
    if (!isReady || !client) {
      return res.status(503).json({
        success: false,
        message: 'WhatsApp client not ready. Scan QR code terlebih dahulu.'
      });
    }

    // Format nomor HP: +62812345678 atau 62812345678
    let chatId = number;
    if (!chatId.includes('@')) {
      // Tambah @c.us untuk format WhatsApp
      chatId = chatId.replace(/\+/g, '') + '@c.us';
    }

    console.log(`📤 Sending message to ${number}...`);

    // Kirim pesan
    const result = await client.sendMessage(chatId, message);

    console.log(`✅ Message sent to ${number}`);

    res.status(200).json({
      success: true,
      message: 'Message sent successfully',
      number: number,
      messageId: result.id,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('❌ Send error:', error.message);

    // Distinguish antara error tipe
    if (error.message.includes('Chat not found')) {
      return res.status(400).json({
        success: false,
        message: 'Nomor HP tidak valid atau chat tidak ditemukan'
      });
    }

    res.status(500).json({
      success: false,
      message: error.message || 'Failed to send message'
    });
  }
});

// API: Send message with media
app.post('/api/send-message-with-media', validateApiKey, async (req, res) => {
  try {
    const { number, message, mediaUrl } = req.body;

    if (!number || !message || !mediaUrl) {
      return res.status(400).json({
        success: false,
        message: 'number, message, dan mediaUrl harus diisi'
      });
    }

    if (!isReady || !client) {
      return res.status(503).json({
        success: false,
        message: 'WhatsApp client not ready'
      });
    }

    let chatId = number;
    if (!chatId.includes('@')) {
      chatId = chatId.replace(/\+/g, '') + '@c.us';
    }

    console.log(`📤 Sending message with media to ${number}...`);

    // Import untuk media
    const MessageMedia = require('whatsapp-web.js').MessageMedia;

    // Download media dari URL
    const response = await fetch(mediaUrl);
    const buffer = await response.buffer();
    const mimetype = response.headers.get('content-type');
    const filename = mediaUrl.split('/').pop();

    const media = new MessageMedia(mimetype, buffer.toString('base64'), filename);
    const result = await client.sendMessage(chatId, media, { caption: message });

    console.log(`✅ Message with media sent to ${number}`);

    res.status(200).json({
      success: true,
      message: 'Message with media sent successfully',
      number: number,
      messageId: result.id
    });

  } catch (error) {
    console.error('❌ Send error:', error.message);
    res.status(500).json({
      success: false,
      message: error.message || 'Failed to send message'
    });
  }
});

// API: Get QR Code (untuk restart)
app.post('/api/logout', validateApiKey, async (req, res) => {
  try {
    if (client) {
      await client.destroy();
      isReady = false;
      initWhatsApp();  // Re-initialize
      
      res.json({
        success: true,
        message: 'Client logged out. Scan QR code baru untuk login.'
      });
    } else {
      res.status(400).json({
        success: false,
        message: 'Client not initialized'
      });
    }
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
});

// API: Get chat list
app.get('/api/chats', validateApiKey, async (req, res) => {
  try {
    if (!isReady || !client) {
      return res.status(503).json({
        success: false,
        message: 'WhatsApp client not ready'
      });
    }

    const chats = await client.getChats();
    
    res.json({
      success: true,
      count: chats.length,
      chats: chats.map(chat => ({
        id: chat.id,
        name: chat.name,
        isGroup: chat.isGroup,
        unreadCount: chat.unreadCount
      }))
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
});

// ─── Static Page untuk testing ──────────────────────────────────────────────

app.get('/', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>WhatsApp.js Server</title>
      <style>
        body { font-family: Arial; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 8px; max-width: 600px; }
        h1 { color: #25D366; }
        .status { padding: 15px; margin: 15px 0; border-radius: 5px; }
        .ready { background: #c8e6c9; color: #2e7d32; }
        .not-ready { background: #ffccbc; color: #d84315; }
        .api { background: #f3e5f5; padding: 15px; margin: 15px 0; border-radius: 5px; font-family: monospace; }
        button { padding: 10px 20px; margin: 5px; cursor: pointer; border: none; border-radius: 5px; background: #25D366; color: white; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>✅ WhatsApp.js Server</h1>
        <p>Server is running on port <strong>${PORT}</strong></p>
        
        <div class="status ${isReady ? 'ready' : 'not-ready'}">
          <strong>Status:</strong> ${isReady ? '✅ READY' : '⏳ NOT READY - Scan QR Code'}
        </div>

        <h3>📌 API Endpoints</h3>
        <div class="api">
          GET /api/health<br>
          GET /api/status<br>
          POST /api/send-message<br>
          POST /api/send-message-with-media<br>
          GET /api/chats<br>
          POST /api/logout
        </div>

        <h3>🔧 Test Send Message</h3>
        <input type="text" id="phone" placeholder="+62812345678" value="+62812345678">
        <input type="text" id="msg" placeholder="Message" value="Test message">
        <button onclick="sendTest()">Send</button>
        <pre id="result"></pre>

        <script>
          async function sendTest() {
            const phone = document.getElementById('phone').value;
            const msg = document.getElementById('msg').value;
            
            try {
              const res = await fetch('/api/send-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ number: phone, message: msg })
              });
              const data = await res.json();
              document.getElementById('result').textContent = JSON.stringify(data, null, 2);
            } catch (e) {
              document.getElementById('result').textContent = 'Error: ' + e.message;
            }
          }

          // Auto refresh status
          setInterval(async () => {
            const res = await fetch('/api/status');
            const data = await res.json();
            document.querySelector('.status').className = 'status ' + (data.ready ? 'ready' : 'not-ready');
            document.querySelector('.status').innerHTML = '<strong>Status:</strong> ' + (data.ready ? '✅ READY' : '⏳ NOT READY');
          }, 5000);
        </script>
      </div>
    </body>
    </html>
  `);
});

// ─── Start Server ───────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`\n🚀 WhatsApp.js Server running on http://localhost:${PORT}\n`);
  console.log('📱 Tunggu sampai QR Code muncul, lalu scan dengan WhatsApp di HP Anda.\n');
});

// ─── Graceful Shutdown ──────────────────────────────────────────────────────

process.on('SIGINT', async () => {
  console.log('\n👋 Shutting down...');
  if (client) {
    await client.destroy();
  }
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n👋 Shutting down...');
  if (client) {
    await client.destroy();
  }
  process.exit(0);
});
