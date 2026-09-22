import json
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import or_

from app import db
from app.models import Conversation, Customer, Message
from app.services.bot_service import process_incoming_message
from app.services.whatsapp_service import send_whatsapp_message


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
    if not value:
        return None

    value = str(value).strip()

    if value.startswith("CO."):
        return None

    digits = "".join(ch for ch in value if ch.isdigit())

    if 8 <= len(digits) <= 15:
        return digits

    return None


MEDIA_MESSAGE_TYPES = {"image", "document", "audio", "video", "sticker"}


def _extract_incoming_content(msg):
    """
    Return a readable text representation while preserving the original
    WhatsApp media payload in raw_payload.
    """
    msg_type = msg.get("type")

    if msg_type == "text":
        return msg.get("text", {}).get("body")

    if msg_type == "interactive":
        interactive = msg.get("interactive", {})

        if interactive.get("type") == "list_reply":
            return interactive.get("list_reply", {}).get("id")

        if interactive.get("type") == "button_reply":
            return interactive.get("button_reply", {}).get("id")

        return None

    if msg_type in MEDIA_MESSAGE_TYPES:
        media = msg.get(msg_type, {}) or {}
        caption = (media.get("caption") or "").strip()

        if caption:
            return caption

        if msg_type == "document":
            filename = (media.get("filename") or "").strip()
            return f"[Document: {filename}]" if filename else "[Document]"

        labels = {
            "image": "[Image]",
            "audio": "[Audio]",
            "video": "[Video]",
            "sticker": "[Sticker]",
        }
        return labels.get(msg_type, "[Media]")

    return None


def _find_active_handoff_conversation(
    recipient,
    customer_phone=None,
    from_user_id=None,
):
    identifiers = {
        str(value).strip()
        for value in (recipient, customer_phone, from_user_id)
        if value
    }

    filters = [
        Conversation.whatsapp_number.in_(identifiers),
    ]

    if customer_phone:
        filters.append(Customer.phone == customer_phone)
        filters.append(Customer.whatsapp_number == customer_phone)

    if from_user_id:
        filters.append(Customer.whatsapp_number == from_user_id)

    return (
        Conversation.query
        .outerjoin(Customer, Customer.id == Conversation.customer_id)
        .filter(
            Conversation.human_handoff.is_(True),
            Conversation.current_state != "CLOSED",
            or_(*filters),
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .first()
    )


def _store_handoff_message(
    conversation,
    recipient,
    incoming_text,
    msg,
    customer_phone=None,
    customer_username=None,
    profile_name=None,
):
    context = dict(conversation.context or {})

    if customer_phone:
        context["customer_phone"] = str(customer_phone).strip()

    if customer_username:
        context["customer_username"] = str(customer_username).strip()

    if profile_name:
        context["profile_name"] = str(profile_name).strip()

    conversation.context = context

    if recipient:
        conversation.whatsapp_number = str(recipient).strip()

    conversation.updated_at = datetime.utcnow()

    message = Message(
        conversation_id=conversation.id,
        whatsapp_message_id=msg.get("id"),
        direction="inbound",
        message_type=msg.get("type", "text"),
        content=incoming_text,
        raw_payload=msg,
    )

    db.session.add(message)
    db.session.commit()

    print(
        "HUMAN HANDOFF MESSAGE STORED:",
        {
            "conversation_id": conversation.id,
            "recipient": conversation.whatsapp_number,
            "message_id": message.id,
        },
        flush=True,
    )


@webhook_bp.route("/webhook", methods=["POST"])
def receive_webhook():
    data = request.get_json(silent=True) or {}

    print(
        "WEBHOOK RECIBIDO:",
        json.dumps(data, ensure_ascii=False),
        flush=True,
    )

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                for status in value.get("statuses", []):
                    print(
                        "WHATSAPP STATUS:",
                        json.dumps(status, ensure_ascii=False),
                        flush=True,
                    )

                contact_data = _extract_contact_data(value)

                for msg in value.get("messages", []):
                    from_number = msg.get("from")
                    from_user_id = (
                        msg.get("from_user_id")
                        or contact_data["user_id"]
                    )

                    recipient = (
                        from_number
                        or from_user_id
                        or contact_data["wa_id"]
                    )

                    if not recipient:
                        print(
                            "Webhook message ignored: no recipient identifier",
                            flush=True,
                        )
                        continue

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
                    incoming_text = _extract_incoming_content(msg)

                    if not incoming_text:
                        print(
                            "Webhook message ignored: unsupported message type",
                            msg_type,
                            flush=True,
                        )
                        continue

                    handoff_conversation = _find_active_handoff_conversation(
                        recipient,
                        customer_phone=customer_phone,
                        from_user_id=from_user_id,
                    )

                    if handoff_conversation:
                        _store_handoff_message(
                            handoff_conversation,
                            recipient,
                            incoming_text,
                            msg,
                            customer_phone=customer_phone,
                            customer_username=customer_username,
                            profile_name=profile_name,
                        )
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

    except Exception as exc:
        db.session.rollback()
        print(
            f"Webhook error: {type(exc).__name__}: {exc}",
            flush=True,
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

    handoff_conversation = _find_active_handoff_conversation(
        phone,
        customer_phone=_normalize_customer_phone(phone),
    )

    if handoff_conversation:
        simulated_msg = {
            "id": None,
            "type": "text",
            "text": {"body": message},
        }
        _store_handoff_message(
            handoff_conversation,
            phone,
            message,
            simulated_msg,
            customer_phone=_normalize_customer_phone(phone),
            customer_username=username,
            profile_name=profile_name,
        )
        return jsonify({
            "phone": phone,
            "incoming": message,
            "reply": None,
            "human_handoff": True,
        })

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
        "human_handoff": False,
    })
