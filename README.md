# 🏠 KostPay — Manajemen Pembayaran Kost

Aplikasi web berbasis **Python Flask** untuk mengelola pembayaran kost, lengkap dengan fitur upload bukti transfer.

---

## 📁 Struktur File

```
kost_app/
│
├── run.py                  # Entry point — jalankan ini
├── app.py                  # Flask app factory & blueprint registration
├── config.py               # Konfigurasi global (folder, secret key, dll.)
│
├── models/                 # Layer database
│   ├── database.py         # Koneksi SQLite & inisialisasi tabel
│   ├── penghuni_model.py   # CRUD penghuni
│   ├── tagihan_model.py    # CRUD tagihan bulanan
│   └── pembayaran_model.py # CRUD pembayaran & bukti transfer
│
├── routes/                 # Layer routing (Blueprint)
│   ├── auth_routes.py      # Login / Logout
│   ├── dashboard_routes.py # Halaman dashboard & statistik
│   ├── penghuni_routes.py  # CRUD penghuni
│   ├── tagihan_routes.py   # Kelola tagihan
│   └── pembayaran_routes.py# Catat pembayaran + upload bukti
│
├── utils/                  # Helper & utilitas
│   ├── auth.py             # Decorator login_required
│   ├── upload_helper.py    # Validasi & simpan file upload
│   └── format_helper.py    # Format Rupiah, nama bulan, badge status
│
├── templates/              # Halaman HTML (Jinja2)
│   ├── base.html           # Layout utama dengan sidebar
│   ├── login.html
│   ├── dashboard.html
│   ├── penghuni/
│   │   ├── index.html
│   │   └── form.html
│   ├── tagihan/
│   │   ├── index.html
│   │   ├── detail.html
│   │   └── form.html
│   └── pembayaran/
│       ├── index.html
│       └── form.html
│
├── static/
│   └── uploads/            # File bukti transfer tersimpan di sini
│
├── kost.db                 # Database SQLite (auto-dibuat)
└── requirements.txt
```

---

## 🚀 Cara Menjalankan

### 1. Install dependencies
```bash
pip install flask werkzeug pillow
```

### 2. Jalankan aplikasi
```bash
python run.py
```

### 3. Buka browser
```
http://localhost:5000
```

**Login default:** `admin` / `admin123`

---

## ✨ Fitur

| Fitur | Keterangan |
|-------|-----------|
| 🔐 Login Admin | Autentikasi session-based dengan password hash |
| 👤 Kelola Penghuni | Tambah, edit, nonaktifkan, hapus penghuni |
| 🧾 Tagihan Bulanan | Buat tagihan manual atau generate otomatis semua penghuni |
| 💰 Catat Pembayaran | Record pembayaran dengan metode: transfer, tunai, QRIS, dompet digital |
| 📎 Upload Bukti | Upload gambar (JPG, PNG) atau PDF sebagai bukti transfer |
| ✅ Verifikasi | Admin bisa verifikasi/batalkan verifikasi bukti pembayaran |
| 📊 Dashboard | Ringkasan statistik, pemasukan bulan ini, tagihan belum lunas |
| 🔍 Filter | Filter tagihan berdasarkan bulan dan status |

---

## ⚙️ Konfigurasi

Edit `config.py` untuk mengubah:
- `SECRET_KEY` — ganti dengan string acak yang aman
- `MAX_CONTENT_LENGTH` — batas ukuran upload (default 5MB)
- `ALLOWED_EXTENSIONS` — ekstensi file yang diizinkan

---

## 🗄️ Database

Menggunakan **SQLite** built-in Python. File `kost.db` dibuat otomatis saat pertama dijalankan.

Tabel:
- `penghuni` — data penghuni kost
- `tagihan` — tagihan sewa per bulan
- `pembayaran` — riwayat pembayaran + nama file bukti
- `admin` — akun administrator
