# 🤖 Panduan Setup Chatbot AI untuk Kost App
## Semua file yang dibutuhkan sudah dibuat. Ikuti langkah berikut.

---

## 📁 File yang Perlu Ditambahkan ke Proyek

```
kost_app/
├── routes/
│   ├── chatbot_routes.py          ← BARU (salin dari output)
│   └── wa_server_routes_PATCH.py  ← BARU (panduan patch WA)
├── utils/
│   ├── chatbot_engine.py          ← BARU (salin dari output)
│   └── wa_chatbot_handler.py      ← BARU (salin dari output)
└── templates/
    └── chatbot_widget.html        ← BARU (salin dari output)
```

---

## 🔑 LANGKAH 1 — Dapatkan Anthropic API Key

1. Buka https://console.anthropic.com
2. Daftar / login
3. Klik **API Keys** → **Create Key**
4. Salin key-nya (format: `sk-ant-...`)

---

## ⚙️ LANGKAH 2 — Set Environment Variable

### Windows (jalankan sekali di CMD sebagai Admin):
```cmd
setx ANTHROPIC_API_KEY "sk-ant-xxxxxxxxxxxxx" /M
```

### Atau tambahkan di `jalankan.bat`:
```bat
cd C:\Users\User\Desktop\last\kost_app_05132026-KirimWa
set ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
python app.py
pause
```

---

## 🔌 LANGKAH 3 — Daftarkan Blueprint di app.py

Tambahkan di `app.py`:

```python
# Di bagian import blueprint (baris ~20)
from routes.chatbot_routes import chatbot_bp

# Di bagian register blueprint (baris ~50)
app.register_blueprint(chatbot_bp)
```

---

## 💬 LANGKAH 4 — Tambahkan Widget Chat di Template

Buka `templates/base.html` (atau template utama Anda), tambahkan sebelum `</body>`:

```html
{% include 'chatbot_widget.html' %}
```

Jika ingin hanya muncul di halaman publik (bukan halaman admin), tambahkan kondisi:

```html
{% if not session.get('admin_id') %}
  {% include 'chatbot_widget.html' %}
{% endif %}
```

---

## 📱 LANGKAH 5 — Integrasi Auto-Reply WhatsApp

Buka `routes/wa_server_routes.py` dan lakukan 2 perubahan:

### A. Tambahkan import di atas file:
```python
import threading
from utils.wa_chatbot_handler import handle_incoming_wa
```

### B. Di dalam fungsi penerima pesan WA, tambahkan:
```python
# Setelah mendapatkan variabel 'sender' dan 'text'
def _do_auto_reply(s, t):
    reply = handle_incoming_wa(s, t)
    if reply:
        # Ganti sesuai cara kirim di app Anda, contoh:
        kirim_pesan_wa(s, reply)   # atau requests.post ke WA server

threading.Thread(target=_do_auto_reply, args=(sender, text), daemon=True).start()
```

> ⚠️ Jalankan di thread terpisah agar tidak memperlambat response webhook.

---

## 🧪 LANGKAH 6 — Test

### Test widget web:
1. Jalankan `python app.py`
2. Buka http://localhost:5000
3. Klik ikon 💬 di pojok kanan bawah
4. Coba tanya: "Ada kamar kosong?" atau "Berapa harga sewa?"

### Test API langsung:
```bash
curl -X POST http://localhost:5000/api/chatbot \
  -H "Content-Type: application/json" \
  -d '{"message": "Ada kamar kosong?", "history": []}'
```

---

## 🔧 Kustomisasi

### Ubah nama/info kost
Edit `utils/chatbot_engine.py`, bagian `info_umum`:
```python
info_umum = """
- Nama kost: Kost XXXX         ← ganti nama kost
- WiFi: tersedia / tidak       ← sesuaikan
- Parkir: motor & mobil        ← sesuaikan
- Jam malam: 23.00 WIB         ← sesuaikan
...
"""
```

### Tambah kamar kosong manual
Jika ada kamar yang tidak ada di DB penghuni tapi kosong, tambahkan di `info_umum`.

### Batasi chatbot hanya untuk jam tertentu
Tambahkan pengecekan waktu di `chatbot_engine.py`:
```python
from datetime import datetime
jam = datetime.now().hour
if jam < 6 or jam > 23:
    return "Maaf, chatbot aktif pukul 06.00–23.00 WIB. Silakan hubungi admin besok 😊"
```

---

## ❓ FAQ

**Q: Chatbot membalas terlalu panjang?**
A: Edit `max_tokens=1024` di `chatbot_engine.py` menjadi `max_tokens=512`

**Q: Chatbot tidak tahu info tertentu?**
A: Tambahkan info di bagian `info_umum` di `chatbot_engine.py`

**Q: Auto-reply WA tidak jalan?**
A: Pastikan endpoint penerima WA di `wa_server_routes.py` sudah dipatch. 
   Cek log terminal saat ada pesan masuk.

**Q: Biaya API Anthropic?**
A: ~$0.003 per 1000 token. Untuk 100 chat/hari ≈ Rp 5.000–10.000/bulan.

---

## 📞 Alur Pesan WA

```
Pengirim WA → Baileys (WA-Web) → wa_server_routes.py
                                         ↓
                              wa_chatbot_handler.py
                                         ↓
                              chatbot_engine.py → Anthropic API
                                         ↓
                              Balasan → kirim_wa → Pengirim
```
