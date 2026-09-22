import hmac
import secrets
from datetime import datetime, timezone
from functools import wraps
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from sqlalchemy import or_

from app import db
from app.models import Conversation, Customer, Message
from app.services.whatsapp_service import (
    download_whatsapp_media,
    send_whatsapp_message,
)


management_bp = Blueprint(
    "management",
    __name__,
    url_prefix="/chatbot/gestion",
    template_folder="../templates",
)


def _management_timezone():
    timezone_name = current_app.config.get("TIMEZONE", "America/Bogota")

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        current_app.logger.warning(
            "Invalid TIMEZONE %s; falling back to America/Bogota",
            timezone_name,
        )
        return ZoneInfo("America/Bogota")


def _local_datetime(value):
    """
    Datetimes in the current schema are stored as naive UTC values.
    Attach UTC explicitly and convert only when presenting them.
    """
    if not value:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(_management_timezone())


def _local_isoformat(value):
    local_value = _local_datetime(value)
    return local_value.isoformat() if local_value else None


def _format_local_datetime(value, fmt="%Y-%m-%d %H:%M:%S"):
    local_value = _local_datetime(value)
    return local_value.strftime(fmt) if local_value else ""


def _admin_token_is_configured():
    return bool(current_app.config.get("CHATBOT_ADMIN_TOKEN"))


def _is_authenticated():
    return session.get("chatbot_management_authenticated") is True


def _csrf_token():
    token = session.get("chatbot_management_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["chatbot_management_csrf"] = token
    return token


def _valid_csrf():
    expected = session.get("chatbot_management_csrf")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def management_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _admin_token_is_configured():
            abort(503, description="CHATBOT_ADMIN_TOKEN is not configured")

        if not _is_authenticated():
            return redirect(url_for("management.login"))

        return view(*args, **kwargs)

    return wrapped


def _conversation_customer(conversation):
    if not conversation.customer_id:
        return None
    return db.session.get(Customer, conversation.customer_id)


def _display_name(conversation):
    context = dict(conversation.context or {})
    customer = _conversation_customer(conversation)

    return (
        context.get("profile_name")
        or context.get("customer_name")
        or (customer.name if customer else None)
        or "WhatsApp customer"
    )


def _display_contact(conversation):
    context = dict(conversation.context or {})
    customer = _conversation_customer(conversation)

    phone = context.get("customer_phone") or (customer.phone if customer else None)
    username = context.get("customer_username")

    if phone:
        phone = str(phone).strip()
        if not phone.startswith("+"):
            phone = "+" + phone
        return phone

    if username:
        username = str(username).strip()
        if not username.startswith("@"):
            username = "@" + username
        return username

    return conversation.whatsapp_number


MEDIA_MESSAGE_TYPES = {"image", "document", "audio", "video", "sticker"}


def _message_media_metadata(message):
    message_type = message.message_type or "text"

    if message_type not in MEDIA_MESSAGE_TYPES:
        return None

    payload = message.raw_payload or {}
    media = payload.get(message_type, {}) or {}
    media_id = media.get("id")

    if not media_id:
        return None

    filename = media.get("filename")

    if not filename:
        filename = {
            "image": f"image-{message.id}",
            "document": f"document-{message.id}",
            "audio": f"audio-{message.id}",
            "video": f"video-{message.id}",
            "sticker": f"sticker-{message.id}",
        }.get(message_type, f"media-{message.id}")

    return {
        "id": str(media_id),
        "mime_type": media.get("mime_type"),
        "filename": filename,
        "caption": media.get("caption"),
        "url": url_for(
            "management.message_media",
            message_id=message.id,
        ),
    }


def _serialize_message(message):
    return {
        "id": message.id,
        "direction": message.direction,
        "content": message.content or "",
        "message_type": message.message_type or "text",
        "media": _message_media_metadata(message),
        "created_at": _local_isoformat(message.created_at),
    }


def _conversation_identifiers(conversation):
    context = dict(conversation.context or {})
    customer = _conversation_customer(conversation)

    identifiers = {
        str(value).strip()
        for value in (
            conversation.whatsapp_number,
            context.get("customer_phone"),
            customer.whatsapp_number if customer else None,
            customer.phone if customer else None,
        )
        if value
    }

    phone_identifiers = {
        value.lstrip("+")
        for value in identifiers
        if not value.startswith("CO.")
    }

    return identifiers, phone_identifiers


def _previous_advisor_conversations(conversation):
    identifiers, phone_identifiers = _conversation_identifiers(conversation)

    relation_filters = []

    if conversation.customer_id:
        relation_filters.append(
            Conversation.customer_id == conversation.customer_id
        )

    if identifiers:
        relation_filters.append(
            Conversation.whatsapp_number.in_(identifiers)
        )
        relation_filters.append(
            Customer.whatsapp_number.in_(identifiers)
        )

    if phone_identifiers:
        relation_filters.append(
            Customer.phone.in_(phone_identifiers)
        )

    if not relation_filters:
        return []

    return (
        Conversation.query
        .outerjoin(Customer, Customer.id == Conversation.customer_id)
        .filter(
            Conversation.id != conversation.id,
            Conversation.current_state == "CLOSED",
            or_(*relation_filters),
        )
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .all()
    )


def _history_item(conversation):
    first_message = (
        Message.query
        .filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .first()
    )
    last_message = (
        Message.query
        .filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )

    return {
        "conversation": conversation,
        "name": _display_name(conversation),
        "contact": _display_contact(conversation),
        "first_message": first_message,
        "last_message": last_message,
    }


@management_bp.context_processor
def inject_management_context():
    return {
        "management_csrf_token": _csrf_token,
        "management_local_datetime": _format_local_datetime,
    }


@management_bp.route("/login", methods=["GET", "POST"])
def login():
    if not _admin_token_is_configured():
        return render_template(
            "management/login.html",
            configuration_error=True,
        ), 503

    if _is_authenticated():
        return redirect(url_for("management.inbox"))

    error = None

    if request.method == "POST":
        supplied = request.form.get("token", "")
        expected = current_app.config.get("CHATBOT_ADMIN_TOKEN", "")

        if hmac.compare_digest(str(supplied), str(expected)):
            session.clear()
            session.permanent = True
            session["chatbot_management_authenticated"] = True
            session["chatbot_management_csrf"] = secrets.token_urlsafe(32)
            return redirect(url_for("management.inbox"))

        error = "Invalid access token."

    return render_template(
        "management/login.html",
        error=error,
        configuration_error=False,
    )


@management_bp.route("/logout", methods=["POST"])
@management_required
def logout():
    if not _valid_csrf():
        abort(400, description="Invalid CSRF token")

    session.clear()
    return redirect(url_for("management.login"))


@management_bp.route("/")
@management_required
def inbox():
    conversations = (
        Conversation.query
        .filter(
            Conversation.human_handoff.is_(True),
            Conversation.current_state != "CLOSED",
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .all()
    )

    items = []

    for conversation in conversations:
        last_message = (
            Message.query
            .filter_by(conversation_id=conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .first()
        )

        items.append({
            "conversation": conversation,
            "name": _display_name(conversation),
            "contact": _display_contact(conversation),
            "last_message": last_message,
        })

    return render_template(
        "management/inbox.html",
        items=items,
    )


@management_bp.route("/conversation/<int:conversation_id>")
@management_required
def conversation_detail(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)

    if not conversation:
        abort(404)

    messages = (
        Message.query
        .filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    history_items = [
        _history_item(item)
        for item in _previous_advisor_conversations(conversation)
    ]

    return render_template(
        "management/conversation.html",
        conversation=conversation,
        customer_name=_display_name(conversation),
        customer_contact=_display_contact(conversation),
        messages=messages,
        history_items=history_items,
    )


@management_bp.route(
    "/conversation/<int:conversation_id>/history/<int:history_id>"
)
@management_required
def conversation_history(conversation_id, history_id):
    conversation = db.session.get(Conversation, conversation_id)
    history = db.session.get(Conversation, history_id)

    if not conversation or not history:
        abort(404)

    allowed_ids = {
        item.id
        for item in _previous_advisor_conversations(conversation)
    }

    if history.id not in allowed_ids:
        abort(404)

    messages = (
        Message.query
        .filter_by(conversation_id=history.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    return jsonify({
        "conversation_id": history.id,
        "name": _display_name(history),
        "contact": _display_contact(history),
        "created_at": _local_isoformat(history.created_at),
        "updated_at": _local_isoformat(history.updated_at),
        "messages": [_serialize_message(message) for message in messages],
    })


@management_bp.route(
    "/conversation/<int:conversation_id>/messages"
)
@management_required
def conversation_messages(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)

    if not conversation:
        abort(404)

    after_id = request.args.get("after", type=int, default=0)

    messages = (
        Message.query
        .filter(
            Message.conversation_id == conversation.id,
            Message.id > after_id,
        )
        .order_by(Message.id.asc())
        .all()
    )

    return jsonify({
        "conversation_id": conversation.id,
        "human_handoff": (
            conversation.human_handoff
            and conversation.current_state != "CLOSED"
        ),
        "messages": [_serialize_message(message) for message in messages],
    })


@management_bp.route("/message/<int:message_id>/media")
@management_required
def message_media(message_id):
    message = db.session.get(Message, message_id)

    if not message:
        abort(404)

    metadata = _message_media_metadata(message)

    if not metadata:
        abort(404)

    try:
        media = download_whatsapp_media(metadata["id"])
    except Exception:
        current_app.logger.exception(
            "Unable to download WhatsApp media message %s",
            message.id,
        )
        abort(502, description="Unable to retrieve WhatsApp media")

    filename = str(metadata.get("filename") or f"media-{message.id}")
    filename = filename.replace('"', "").replace("\\", "_").replace("/", "_")

    response = Response(
        media["content"],
        mimetype=media.get("mime_type") or metadata.get("mime_type")
        or "application/octet-stream",
    )
    response.headers["Content-Disposition"] = (
        f'inline; filename="{filename}"'
    )
    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@management_bp.route(
    "/conversation/<int:conversation_id>/send",
    methods=["POST"],
)
@management_required
def send_message(conversation_id):
    if not _valid_csrf():
        abort(400, description="Invalid CSRF token")

    conversation = db.session.get(Conversation, conversation_id)

    if not conversation:
        abort(404)

    if (
        not conversation.human_handoff
        or conversation.current_state == "CLOSED"
    ):
        flash("This conversation is no longer assigned to an advisor.", "warning")
        return redirect(
            url_for(
                "management.conversation_detail",
                conversation_id=conversation.id,
            )
        )

    text = (request.form.get("message") or "").strip()

    if not text:
        flash("Write a message before sending.", "warning")
        return redirect(
            url_for(
                "management.conversation_detail",
                conversation_id=conversation.id,
            )
        )

    try:
        response = send_whatsapp_message(
            conversation.whatsapp_number,
            text,
        )
    except Exception as exc:
        current_app.logger.exception(
            "Unable to send advisor WhatsApp message"
        )
        flash(f"WhatsApp delivery failed: {exc}", "danger")
        return redirect(
            url_for(
                "management.conversation_detail",
                conversation_id=conversation.id,
            )
        )

    whatsapp_message_id = None
    response_messages = (
        response.get("messages", [])
        if isinstance(response, dict)
        else []
    )
    if response_messages:
        whatsapp_message_id = response_messages[0].get("id")

    message = Message(
        conversation_id=conversation.id,
        whatsapp_message_id=whatsapp_message_id,
        direction="outbound",
        message_type="text",
        content=text,
        raw_payload={"source": "management_portal"},
    )

    conversation.updated_at = datetime.utcnow()
    db.session.add(message)
    db.session.commit()

    return redirect(
        url_for(
            "management.conversation_detail",
            conversation_id=conversation.id,
        )
    )


@management_bp.route(
    "/conversation/<int:conversation_id>/close",
    methods=["POST"],
)
@management_required
def close_conversation(conversation_id):
    if not _valid_csrf():
        abort(400, description="Invalid CSRF token")

    conversation = db.session.get(Conversation, conversation_id)

    if not conversation:
        abort(404)

    context = dict(conversation.context or {})
    identity_context = {
        key: context[key]
        for key in (
            "customer_phone",
            "customer_username",
            "profile_name",
        )
        if context.get(key)
    }

    # Keep this record as an archived advisor session. human_handoff stays
    # True so bot_service will create a fresh non-handoff conversation on
    # the customer's next message. The webhook explicitly ignores CLOSED
    # handoff records.
    conversation.context = identity_context
    conversation.current_state = "CLOSED"
    conversation.human_handoff = True
    conversation.updated_at = datetime.utcnow()
    db.session.commit()

    flash(
        "Conversation closed. The chatbot will handle the next message.",
        "success"
    )
    return redirect(url_for("management.inbox"))
