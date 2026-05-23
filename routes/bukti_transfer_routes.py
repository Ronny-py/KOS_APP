"""
routes/bukti_transfer_routes.py
Endpoint publik (tidak perlu login) untuk penghuni kirim bukti transfer
lewat chatbot di halaman login.

Letakkan file ini di folder routes/ lalu daftarkan di app.py.
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
import sqlite3
from config import DATABASE, UPLOAD_FOLDER, ALLOWED_EXTENSIONS

bukti_transfer_bp = Blueprint('bukti_transfer', __name__)


def _get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


@bukti_transfer_bp.route('/api/bukti-transfer', methods=['POST'])
def terima_bukti():
    nama_input = (request.form.get('nama') or '').strip()
    file       = request.files.get('bukti')

    # ── Validasi input ──────────────────────────────────────────────────────
    if not nama_input:
        return jsonify({'reply': '❌ Nama / nomor kamar tidak boleh kosong.'}), 400
    if not file or file.filename == '':
        return jsonify({'reply': '❌ File bukti tidak ditemukan.'}), 400

    ext = os.path.splitext(file.filename)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'reply': '❌ Format tidak didukung. Gunakan JPG, PNG, atau PDF.'}), 400

    db = _get_db()
    try:
        q = nama_input.upper()

        # ── 1. Cari penghuni (exact match nama atau nomor_kamar dulu) ───────
        row = db.execute(
            """
            SELECT  p.*,
                    t.id      AS tagihan_id,
                    t.jumlah  AS t_jumlah,
                    t.bulan   AS t_bulan,
                    t.status  AS t_status
            FROM    penghuni p
            LEFT JOIN tagihan t
                   ON t.penghuni_id = p.id
                  AND t.bulan = strftime('%Y-%m', 'now', 'localtime')
            WHERE   p.aktif = 1
              AND  (UPPER(p.nama) = ? OR UPPER(p.nomor_kamar) = ?)
            ORDER BY t.id DESC
            LIMIT 1
            """,
            (q, q)
        ).fetchone()

        # Fallback: partial match nama
        if not row:
            row = db.execute(
                """
                SELECT  p.*,
                        t.id      AS tagihan_id,
                        t.jumlah  AS t_jumlah,
                        t.bulan   AS t_bulan,
                        t.status  AS t_status
                FROM    penghuni p
                LEFT JOIN tagihan t
                       ON t.penghuni_id = p.id
                      AND t.bulan = strftime('%Y-%m', 'now', 'localtime')
                WHERE   p.aktif = 1
                  AND   UPPER(p.nama) LIKE ?
                ORDER BY t.id DESC
                LIMIT 1
                """,
                (f'%{q}%',)
            ).fetchone()

        if not row:
            return jsonify({
                'reply': (
                    f'❌ Penghuni *"{nama_input}"* tidak ditemukan.\n'
                    'Ketik nama lengkap atau nomor kamar sesuai data kost.\n'
                    'Hubungi admin jika butuh bantuan: 08159959605'
                )
            }), 404

        # ── 2. Simpan file ke UPLOAD_FOLDER ────────────────────────────────
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        orig_name = file.filename
        safe_name = f"bukti_{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(UPLOAD_FOLDER, safe_name))

        now         = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tagihan_id  = row['tagihan_id']   # None kalau belum ada tagihan bulan ini
        penghuni_id = row['id']

        # ── 3. Insert record pembayaran (verified=0 → pending verifikasi) ───
        cur = db.execute(
            """
            INSERT INTO pembayaran
              (tagihan_id, penghuni_id, jumlah_bayar, metode,
               bukti_file, catatan, tanggal_bayar, verified)
            VALUES (?, ?, 0, 'transfer', ?, ?, ?, 0)
            """,
            (
                tagihan_id,
                penghuni_id,
                safe_name,
                'Dikirim penghuni via chatbot — menunggu verifikasi admin',
                now,
            )
        )
        pembayaran_id = cur.lastrowid

        # ── 4. Insert ke pembayaran_bukti (tabel multi-file) ─────────────
        db.execute(
            """
            INSERT INTO pembayaran_bukti
              (pembayaran_id, filename, original_name, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (pembayaran_id, safe_name, orig_name, now)
        )

        db.commit()

        # ── 5. Bangun pesan balasan ─────────────────────────────────────────
        nama_penghuni = row['nama']
        kamar         = row['nomor_kamar']
        bulan_raw     = row['t_bulan'] or ''

        try:
            dt = datetime.strptime(bulan_raw, '%Y-%m')
            BULAN = ['Januari','Februari','Maret','April','Mei','Juni',
                     'Juli','Agustus','September','Oktober','November','Desember']
            bulan_label = f"{BULAN[dt.month - 1]} {dt.year}"
        except Exception:
            bulan_label = 'bulan berjalan'

        reply = (
            f'✅ Bukti transfer berhasil diterima!\n\n'
            f'👤 {nama_penghuni} — Kamar {kamar}\n'
            f'📅 Periode: {bulan_label}\n\n'
            f'⏳ Status: Menunggu verifikasi admin.\n'
            f'Admin akan memproses dalam 1×24 jam.\n\n'
            f'Terima kasih 🙏'
        )
        return jsonify({'reply': reply})

    except Exception as e:
        db.rollback()
        current_app.logger.error(f'[bukti-transfer] {e}')
        return jsonify({
            'reply': '⚠️ Terjadi kesalahan server. Hubungi admin: 08159959605'
        }), 500
    finally:
        db.close()
