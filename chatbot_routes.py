"""
routes/chatbot_routes.py
Blueprint chatbot – TANPA AI, langsung dari database.
"""
from flask import Blueprint, request, jsonify, session
from utils.wa_chatbot_handler import handle_web_message

chatbot_bp = Blueprint('chatbot', __name__)


@chatbot_bp.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    """
    Endpoint untuk widget chat di halaman web.
    Body JSON: { "message": "..." }
    """
    data         = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()

    if not user_message:
        return jsonify({'error': 'Pesan kosong'}), 400

    # Gunakan session Flask sebagai ID unik per browser
    session_id = session.get('session_id') or request.remote_addr
    reply = handle_web_message(session_id, user_message)
    return jsonify({'reply': reply})


@chatbot_bp.route('/api/chatbot/wa', methods=['POST'])
def chatbot_wa():
    """
    Endpoint internal – dipanggil oleh wa_server ketika ada pesan WA masuk.
    Body JSON: { "from": "628xxx", "message": "..." }
    """
    data    = request.get_json(silent=True) or {}
    sender  = data.get('from', '')
    message = (data.get('message') or '').strip()

    if not message:
        return jsonify({'reply': ''})

    from utils.wa_chatbot_handler import handle_incoming_wa
    reply = handle_incoming_wa(sender, message)
    return jsonify({'reply': reply})
