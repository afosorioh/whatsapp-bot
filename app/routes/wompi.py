from itsdangerous import BadSignature, URLSafeSerializer
from flask import Blueprint, abort, current_app, render_template, request

from app import db
from app.models import Payment
from app.services.wompi_service import get_transaction


wompi_bp = Blueprint(
    "wompi",
    __name__,
    url_prefix="/chatbot/wompi",
    template_folder="../templates",
)


FINAL_PAYMENT_STATUSES = {"APPROVED", "DECLINED", "VOIDED", "ERROR"}


def _payment_serializer():
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not configured")

    return URLSafeSerializer(
        secret_key,
        salt="wompi-payment-result",
    )


def make_payment_result_token(payment_id):
    return _payment_serializer().dumps({"payment_id": int(payment_id)})


def _payment_from_token(token):
    try:
        data = _payment_serializer().loads(token)
    except BadSignature:
        abort(404)

    payment_id = data.get("payment_id") if isinstance(data, dict) else None
    payment = db.session.get(Payment, payment_id) if payment_id else None

    if not payment or payment.provider != "wompi":
        abort(404)

    return payment


def _expected_payment_link_id(payment):
    raw_payload = dict(payment.raw_payload or {})
    link_id = raw_payload.get("wompi_payment_link_id")

    if not link_id:
        response = raw_payload.get("response") or {}
        link_id = (response.get("data") or {}).get("id")

    if not link_id and payment.payment_url and "/l/" in payment.payment_url:
        link_id = payment.payment_url.rsplit("/l/", 1)[-1].split("?", 1)[0]

    return str(link_id) if link_id else None


def update_payment_from_transaction(payment, transaction_result):
    transaction = transaction_result.get("transaction") or {}
    transaction_id = transaction.get("id")

    if not transaction_id:
        raise RuntimeError("Wompi transaction ID is missing")

    expected_link_id = _expected_payment_link_id(payment)
    transaction_link_id = transaction.get("payment_link_id")

    if (
        expected_link_id
        and transaction_link_id
        and str(expected_link_id) != str(transaction_link_id)
    ):
        raise RuntimeError("Transaction does not belong to this payment link")

    amount_in_cents = transaction.get("amount_in_cents")
    if amount_in_cents is not None:
        expected_amount = int(payment.amount or 0) * 100
        if int(amount_in_cents) != expected_amount:
            raise RuntimeError("Transaction amount does not match payment")

    currency = transaction.get("currency")
    if currency and str(currency).upper() != str(payment.currency or "COP").upper():
        raise RuntimeError("Transaction currency does not match payment")

    raw_payload = dict(payment.raw_payload or {})
    raw_payload["transaction"] = transaction
    raw_payload["transaction_lookup_response"] = transaction_result.get("response")
    raw_payload["transaction_environment"] = transaction_result.get("environment")
    raw_payload["captured_transaction_id"] = str(transaction_id)

    payment.provider_transaction_id = str(transaction_id)
    payment.status = str(transaction.get("status") or "PENDING").upper()
    payment.raw_payload = raw_payload

    return payment.status


def refresh_payment_transaction(payment):
    transaction_id = payment.provider_transaction_id
    raw_payload = dict(payment.raw_payload or {})
    link_id = _expected_payment_link_id(payment)

    # Before Wompi redirects the customer, provider_transaction_id stores the
    # link ID. Only query /transactions after a real transaction ID has been
    # captured and persisted in raw_payload.
    captured_id = raw_payload.get("captured_transaction_id")
    if captured_id:
        transaction_id = captured_id
    elif transaction_id and link_id and str(transaction_id) == str(link_id):
        return payment.status

    if not transaction_id:
        return payment.status

    result = get_transaction(transaction_id)
    status = update_payment_from_transaction(payment, result)
    db.session.commit()
    return status


@wompi_bp.route("/payment-result/<token>", methods=["GET"])
def payment_result(token):
    payment = _payment_from_token(token)
    transaction_id = (request.args.get("id") or "").strip()
    error = None

    if transaction_id:
        try:
            result = get_transaction(transaction_id)
            update_payment_from_transaction(payment, result)
            db.session.commit()
        except Exception as exc:
            current_app.logger.exception(
                "Unable to verify redirected Wompi transaction %s",
                transaction_id,
            )
            error = str(exc)
    else:
        error = "Wompi did not provide a transaction ID in the redirect."

    return render_template(
        "wompi/payment_result.html",
        payment=payment,
        transaction_id=transaction_id or payment.provider_transaction_id,
        error=error,
        is_final=(payment.status or "").upper() in FINAL_PAYMENT_STATUSES,
    )
