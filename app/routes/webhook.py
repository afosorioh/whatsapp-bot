from flask import Blueprint, request, jsonify, current_app
from app.services.bot_service import process_incoming_message
from app.services.whatsapp_service import send_whatsapp_message
import json

webhook_bp = Blueprint("webhook", __name__, url_prefix="/chatbot")


@webhook_bp.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    verify_token = current_app.config.get("WHATSAPP_VERIFY_TOKEN")

    if mode == "subscribe" and token == verify_token:
        return challenge, 200

    return "Forbidden", 403


def _extract_contact_data(value):
    """
    Extrae los datos humanos del contacto que Meta incluya en el webhook.

    Meta puede entregar:
      - wa_id: número de WhatsApp
      - user_id: identificador BSUID (CO.xxxxx)
      - profile.name
      - profile.username

    No todos los campos están presentes en todos los mensajes.
    """
    contacts = value.get("contacts", [])

    if not contacts:
        return {
            "wa_id": None,
            "user_id": None,
            "profile_name": None,
            "username": None,
        }

    contact = contacts[0] or {}
    profile = contact.get("profile", {}) or {}

    return {
        "wa_id": contact.get("wa_id"),
        "user_id": contact.get("user_id"),
        "profile_name": profile.get("name"),
        "username": profile.get("username"),
    }


def _normalize_customer_phone(value):
    """
    Devuelve solo dígitos si value realmente parece un teléfono.
    Evita guardar identificadores BSUID (CO.xxxxx) como teléfono.
    """
    if not value:
        return None

    value = str(value).strip()

    if value.startswith("CO."):
        return None

    digits = "".join(ch for ch in value if ch.isdigit())

    # Un número internacional real debe tener una longitud razonable.
    if 8 <= len(digits) <= 15:
        return digits

    return None


@webhook_bp.route("/webhook", methods=["POST"])
def receive_webhook():
    data = request.get_json(silent=True) or {}

    print(
        "WEBHOOK RECIBIDO:",
        json.dumps(data, ensure_ascii=False),
        flush=True
    )

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Los statuses corresponden a mensajes salientes.
                for status in value.get("statuses", []):
                    print(
                        "WHATSAPP STATUS:",
                        json.dumps(status, ensure_ascii=False),
                        flush=True
                    )

                contact_data = _extract_contact_data(value)

                for msg in value.get("messages", []):
                    from_number = msg.get("from")
                    from_user_id = (
                        msg.get("from_user_id")
                        or contact_data["user_id"]
                    )

                    # Identificador técnico usado para responder al usuario.
                    # Si Meta entrega "from", usamos teléfono; si no, BSUID.
                    recipient = (
                        from_number
                        or from_user_id
                        or contact_data["wa_id"]
                    )

                    if not recipient:
                        print(
                            "Webhook message ignored: no recipient identifier",
                            flush=True
                        )
                        continue

                    # Número humano para entregárselo al asesor.
                    # Puede venir en messages[].from o contacts[].wa_id.
                    customer_phone = (
                        _normalize_customer_phone(from_number)
                        or _normalize_customer_phone(contact_data["wa_id"])
                    )

                    customer_username = contact_data["username"]
                    profile_name = contact_data["profile_name"]

                    print("RECIPIENT:", recipient, flush=True)
                    print("CUSTOMER PHONE:", customer_phone, flush=True)
                    print("CUSTOMER USERNAME:", customer_username, flush=True)
                    print("PROFILE NAME:", profile_name, flush=True)

                    msg_type = msg.get("type")
                    incoming_text = None

                    if msg_type == "text":
                        incoming_text = (
                            msg.get("text", {}).get("body")
                        )

                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})

                        if interactive.get("type") == "list_reply":
                            incoming_text = (
                                interactive
                                .get("list_reply", {})
                                .get("id")
                            )

                        elif interactive.get("type") == "button_reply":
                            incoming_text = (
                                interactive
                                .get("button_reply", {})
                                .get("id")
                            )

                    if not incoming_text:
                        continue

                    reply = process_incoming_message(
                        recipient,
                        incoming_text,
                        customer_phone=customer_phone,
                        customer_username=customer_username,
                        profile_name=profile_name,
                    )

                    if reply:
                        send_whatsapp_message(recipient, reply)

    except Exception as e:
        print(
            f"Webhook error: {type(e).__name__}: {e}",
            flush=True
        )

    return jsonify({"status": "ok"}), 200


@webhook_bp.route("/simulate-message", methods=["POST"])
def simulate_message():
    data = request.get_json(silent=True) or {}

    phone = data.get("phone")
    message = data.get("message")
    username = data.get("username")
    profile_name = data.get("profile_name")

    if not phone or not message:
        return jsonify({
            "error": "phone and message are required"
        }), 400

    reply = process_incoming_message(
        phone,
        message,
        customer_phone=phone,
        customer_username=username,
        profile_name=profile_name,
    )

    return jsonify({
        "phone": phone,
        "incoming": message,
        "reply": reply,
    })
