from functools import wraps
from flask import request, jsonify, current_app


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        expected_key = current_app.config.get("CHATBOT_API_KEY")
        provided_key = request.headers.get("X-API-Key")

        if not expected_key:
            return jsonify({"error": "CHATBOT_API_KEY not configured"}), 500

        if provided_key != expected_key:
            return jsonify({"error": "Unauthorized"}), 401

        return f(*args, **kwargs)

    return decorated
