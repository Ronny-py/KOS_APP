"""
PATCH INSTRUCTIONS
==================
File ini berisi potongan kode yang perlu ditambahkan ke file yang sudah ada.
Ikuti langkah-langkah di bawah ini.

══════════════════════════════════════════════════════════
LANGKAH 1 — utils/migrate_supervisor.py
══════════════════════════════════════════════════════════
Salin file baru:
    utils/migrate_supervisor.py   ← sudah dibuat
    utils/activity_logger.py      ← sudah dibuat
    routes/supervisor_routes.py   ← sudah dibuat
    templates/supervisor/         ← sudah dibuat (5 file HTML)

══════════════════════════════════════════════════════════
LANGKAH 2 — app.py  (tambahkan baris berikut)
══════════════════════════════════════════════════════════
Cari baris:
    from utils.migrate_komplain import migrate_komplain

Tambahkan SETELAH baris tersebut:
    from utils.migrate_supervisor import migrate_supervisor       # ← SUPERVISOR
    from utils.activity_logger    import log_activity             # ← SUPERVISOR

Cari baris:
    from routes.komplain_publik_routes   import komplain_publik_bp

Tambahkan SETELAH baris tersebut:
    from routes.supervisor_routes        import supervisor_bp     # ← SUPERVISOR

Cari baris (di dalam create_app()):
    migrate_komplain()

Tambahkan SETELAH baris tersebut:
    migrate_supervisor()                                          # ← SUPERVISOR

Cari baris (di dalam create_app()):
    app.register_blueprint(komplain_publik_bp)

Tambahkan SETELAH baris tersebut:
    app.register_blueprint(supervisor_bp)                         # ← SUPERVISOR

Cari baris (di dalam create_app(), setelah register blueprint):
    register_context_processors(app)

Tambahkan SETELAH baris tersebut:
    log_activity(app)                                             # ← SUPERVISOR

══════════════════════════════════════════════════════════
LANGKAH 3 — routes/auth_routes.py
══════════════════════════════════════════════════════════
Di bagian import, tambahkan:
    from utils.activity_logger import log_login, get_client_ip

Di fungsi login() — setelah baris yang set session (login sukses), tambahkan:
    log_login(
        admin_id   = admin["id"],
        username   = username,
        ip         = get_client_ip(),
        user_agent = request.headers.get("User-Agent", ""),
        status     = "success"
    )

Di fungsi login() — di bagian login GAGAL (sebelum flash atau return), tambahkan:
    log_login(
        admin_id   = None,
        username   = username,
        ip         = get_client_ip(),
        user_agent = request.headers.get("User-Agent", ""),
        status     = "failed"
    )

══════════════════════════════════════════════════════════
LANGKAH 4 — templates/base.html  (sidebar admin)
══════════════════════════════════════════════════════════
Cari blok nav-section terakhir (Laporan), di BAWAH </div> penutupnya,
tambahkan section baru SEBELUM </nav>:

    {% if session.get('supervisor_id') is none %}
    {# Tampilkan link ke panel supervisor hanya jika BUKAN sedang di panel supervisor #}
    {% endif %}

NOTE: Link supervisor muncul di login page, bukan di sidebar admin.
Supervisor punya sidebar sendiri yang terpisah sepenuhnya.
Akses panel supervisor: /supervisor/login

══════════════════════════════════════════════════════════
LANGKAH 5 — templates/login.html
══════════════════════════════════════════════════════════
Tambahkan link ke bawah hint di login.html, setelah:
    <div class="hint">Default: admin / admin123</div>

Tambahkan:
    <div class="hint" style="margin-top:10px;">
      <a href="/supervisor/login" style="color:#8892a4; font-size:11px; text-decoration:none;">
        🛡️ Login sebagai Supervisor
      </a>
    </div>

══════════════════════════════════════════════════════════
RINGKASAN FILE BARU YANG DITAMBAHKAN
══════════════════════════════════════════════════════════
utils/migrate_supervisor.py
utils/activity_logger.py
routes/supervisor_routes.py
templates/supervisor/login.html
templates/supervisor/base_supervisor.html
templates/supervisor/dashboard.html
templates/supervisor/login_log.html
templates/supervisor/activity_log.html
templates/supervisor/ganti_password.html

══════════════════════════════════════════════════════════
KREDENSIAL DEFAULT
══════════════════════════════════════════════════════════
URL    : /supervisor/login
User   : supervisor
Pass   : supervisor123

Ganti password setelah pertama kali login via menu Ganti Password.
"""
