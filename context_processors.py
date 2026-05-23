"""
utils/context_processors.py
Inject variabel global ke semua template.
"""
from flask import session


def register_context_processors(app):
    @app.context_processor
    def inject_komplain_badge():
        """Tampilkan jumlah komplain baru di sidebar (hanya jika login)."""
        if not session.get('admin_id'):
            return {}
        try:
            from models.database import get_db
            row = get_db().execute(
                "SELECT COUNT(*) c FROM komplain WHERE status='baru'"
            ).fetchone()
            return {'komplain_baru_count': row['c'] if row and row['c'] else 0}
        except Exception:
            return {'komplain_baru_count': 0}
