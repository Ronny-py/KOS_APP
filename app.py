"""
app.py
Flask app factory – titik masuk utama.
"""
import os
from flask import Flask, redirect, url_for
from config import SECRET_KEY, UPLOAD_FOLDER, MAX_CONTENT_LENGTH
from models.database import init_db
from utils.format_helper import rupiah, nama_bulan, status_badge
from utils.migrate_dokumen import migrate_dokumen_penghuni
from utils.migrate_pengeluaran import migrate_pengeluaran
from utils.migrate_admin_expiry import migrate_admin_expiry
from utils.migrate_notif_wa import migrate_notif_wa
from utils.migrate_komplain import migrate_komplain
from utils.migrate_supervisor import migrate_supervisor          # ← SUPERVISOR
from utils.activity_logger    import log_activity               # ← SUPERVISOR

# ── Blueprint imports ──────────────────────────────────────────────────────────
from routes.auth_routes               import auth_bp
from routes.dashboard_routes          import dashboard_bp
from routes.penghuni_routes           import penghuni_bp
from routes.tagihan_routes            import tagihan_bp
from routes.pembayaran_routes         import pembayaran_bp
from routes.laporan_routes            import laporan_bp
from routes.pengeluaran_routes        import pengeluaran_bp
from routes.inventaris_routes         import inventaris_bp
from routes.laporan_inventaris_routes import laporan_inventaris_bp
from routes.notif_wa_routes           import notif_wa_bp
from routes.kirim_wa_routes           import kirim_wa_bp
from routes.chatbot_routes            import chatbot_bp
from routes.bukti_transfer_routes     import bukti_transfer_bp
from routes.wa_scheduler_routes       import wa_scheduler_bp
from routes.komplain_routes           import komplain_bp
from routes.komplain_publik_routes    import komplain_publik_bp
from routes.supervisor_routes         import supervisor_bp       # ← SUPERVISOR


def create_app():
    app = Flask(__name__)
    app.secret_key                   = SECRET_KEY
    app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    with app.app_context():
        init_db()
        migrate_dokumen_penghuni()
        migrate_pengeluaran()
        migrate_admin_expiry()
        migrate_notif_wa()
        migrate_komplain()
        migrate_supervisor()                                      # ← SUPERVISOR

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp,  url_prefix='/dashboard')
    app.register_blueprint(penghuni_bp)
    app.register_blueprint(tagihan_bp)
    app.register_blueprint(pembayaran_bp)
    app.register_blueprint(laporan_bp)
    app.register_blueprint(pengeluaran_bp)
    app.register_blueprint(inventaris_bp)
    app.register_blueprint(laporan_inventaris_bp)
    app.register_blueprint(notif_wa_bp)
    app.register_blueprint(kirim_wa_bp)
    app.register_blueprint(kirim_wa_bp, url_prefix='/wa', name='kirim_wa_wa')
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(bukti_transfer_bp)
    app.register_blueprint(wa_scheduler_bp)
    app.register_blueprint(komplain_bp)
    app.register_blueprint(komplain_publik_bp)
    app.register_blueprint(supervisor_bp)                        # ← SUPERVISOR

    # Context processors
    from utils.context_processors import register_context_processors
    register_context_processors(app)

    # Activity logger (catat setiap akses menu admin)
    log_activity(app)                                            # ← SUPERVISOR

    # Route root → redirect ke dashboard atau login
    @app.route("/")
    def root():
        from flask import session
        if session.get("admin_id"):
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    # Template filters
    app.jinja_env.filters['rupiah']       = rupiah
    app.jinja_env.filters['nama_bulan']   = nama_bulan
    app.jinja_env.filters['status_badge'] = status_badge

    # ── Scheduler notifikasi WA ────────────────────────────────────────────
    import os as _os
    if not app.testing and _os.environ.get("WERKZEUG_RUN_MAIN") != "false":
        try:
            from utils.scheduler import start_scheduler
            start_scheduler(app)
        except Exception as e:
            app.logger.warning(f"Scheduler tidak bisa distart: {e}")

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)

app = create_app()
