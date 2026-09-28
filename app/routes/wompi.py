import hashlib
import hmac

from flask import Blueprint, current_app, jsonify, request

from app import db
from app.models import Payment


wompi_bp = Blueprint(
    "wompi",
    __name__,
    url_prefix="/chatbot/wompi",
)


FINAL_PAYMENT_STATUSES = {"APPROVED", "DECLINED", "VOIDED", "ERROR"}


def _event_property_value(data, path):
    value = data
    for part in str(path).split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def _valid_wompi_signature(payload):
    secret = current_app.config.get("WOMPI_EVENT_SECRET")
    if not secret:
        raise RuntimeError("WOMPI_EVENT_SECRET is not configured")

    signature = payload.get("signature") or {}
    properties = signature.get("properties") or []
    supplied_checksum = (
        request.headers.get("X-Event-Checksum")
        or signature.get("checksum")
        or ""
    )
    timestamp = payload.get("timestamp")
    data = payload.get("data") or {}

    if not properties or timestamp is None or not supplied_checksum:
        return False

    try:
        values = [
            str(_event_property_value(data, property_path))
            for property_path in properties
        ]
    except KeyError:
        return False

    raw = "".join(values) + str(timestamp) + str(secret)
    calculated = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return hmac.compare_digest(
        calculated.lower(),
        str(supplied_checksum).lower(),
    )


def _payment_link_id(payment):
    payload = dict(payment.raw_payload or {})

    direct = payload.get("wompi_payment_link_id")
    if direct:
        return str(direct)

    response = payload.get("response") or {}
    response_data = response.get("data") or {}
    if response_data.get("id"):
        return str(response_data["id"])

    if payment.payment_url and "/l/" in payment.payment_url:
        return payment.payment_url.rsplit("/l/", 1)[-1].split("?", 1)[0]

    # Before a transaction event arrives, the current implementation stores
    # the Wompi payment-link ID in provider_transaction_id.
    if payment.provider_transaction_id:
        return str(payment.provider_transaction_id)

    return None


def _find_payment_by_link_id(payment_link_id):
    candidates = (
        Payment.query
        .filter_by(provider="wompi")
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(500)
        .all()
    )

    for payment in candidates:
        if _payment_link_id(payment) == str(payment_link_id):
            return payment

    return None


@wompi_bp.route("/events", methods=["POST"])
def receive_wompi_event():
    payload = request.get_json(silent=True) or {}

    try:
        if not _valid_wompi_signature(payload):
            current_app.logger.warning("Rejected invalid Wompi event signature")
            return jsonify({"status": "invalid signature"}), 401
    except RuntimeError as exc:
        current_app.logger.error(str(exc))
        return jsonify({"status": "configuration error"}), 503

    if payload.get("event") != "transaction.updated":
        return jsonify({"status": "ignored"}), 200

    transaction = (payload.get("data") or {}).get("transaction") or {}
    payment_link_id = transaction.get("payment_link_id")

    if not payment_link_id:
        # This webhook belongs to the whole Wompi account. Transactions that
        # were not created from a payment link are intentionally ignored.
        return jsonify({"status": "ignored"}), 200

    payment = _find_payment_by_link_id(payment_link_id)

    if not payment:
        current_app.logger.info(
            "Wompi transaction %s belongs to unknown payment link %s",
            transaction.get("id"),
            payment_link_id,
        )
        return jsonify({"status": "not found"}), 200

    status = str(transaction.get("status") or "PENDING").upper()
    transaction_id = transaction.get("id")

    raw_payload = dict(payment.raw_payload or {})
    raw_payload["wompi_payment_link_id"] = str(payment_link_id)
    raw_payload["transaction"] = transaction
    raw_payload["last_event"] = payload

    payment.status = status
    payment.provider_transaction_id = transaction_id or payment.provider_transaction_id
    payment.raw_payload = raw_payload
    db.session.commit()

    current_app.logger.info(
        "Wompi payment %s updated to %s (transaction %s)",
        payment.id,
        status,
        transaction_id,
    )

    return jsonify({
        "status": "updated",
        "payment_id": payment.id,
        "payment_status": status,
        "final": status in FINAL_PAYMENT_STATUSES,
    }), 200
