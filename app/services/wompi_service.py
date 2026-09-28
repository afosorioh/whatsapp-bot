import requests
from flask import current_app


WOMPI_BASE_URLS = {
    "sandbox": "https://sandbox.wompi.co/v1",
    "production": "https://production.wompi.co/v1",
}


def _wompi_environment():
    environment = str(
        current_app.config.get("WOMPI_ENV", "sandbox")
    ).strip().lower()

    if environment not in WOMPI_BASE_URLS:
        raise RuntimeError(
            "WOMPI_ENV must be either sandbox or production"
        )

    return environment


def _wompi_private_key():
    private_key = current_app.config.get("WOMPI_PRIVATE_KEY")

    if not private_key:
        raise RuntimeError("WOMPI_PRIVATE_KEY is not configured")

    environment = _wompi_environment()

    if environment == "sandbox" and not str(private_key).startswith("prv_test_"):
        raise RuntimeError(
            "Sandbox requires a Wompi private key with prefix prv_test_"
        )

    if environment == "production" and not str(private_key).startswith("prv_prod_"):
        raise RuntimeError(
            "Production requires a Wompi private key with prefix prv_prod_"
        )

    return str(private_key)


def create_payment_link(
    amount_cop,
    name,
    description=None,
    redirect_url=None,
):
    """Create a fixed-value, single-use Wompi payment link."""
    environment = _wompi_environment()
    private_key = _wompi_private_key()
    base_url = WOMPI_BASE_URLS[environment]

    amount_cop = int(amount_cop)

    if amount_cop <= 0:
        raise ValueError("Payment amount must be greater than zero")

    payload = {
        "name": str(name)[:150],
        "description": str(
            description or "Pago solicitado por Cervecería Libre"
        )[:255],
        "single_use": True,
        "collect_shipping": False,
        "currency": "COP",
        "amount_in_cents": amount_cop * 100,
    }

    if redirect_url:
        payload["redirect_url"] = str(redirect_url)

    response = requests.post(
        f"{base_url}/payment_links",
        headers={
            "Authorization": f"Bearer {private_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        try:
            error_data = response.json()
            error_message = (
                error_data.get("error", {}).get("message")
                or error_data.get("message")
                or response.text
            )
        except ValueError:
            error_message = response.text

        raise RuntimeError(
            f"Wompi payment link API error {response.status_code}: "
            f"{error_message}"
        )

    data = response.json()
    link_data = data.get("data") or {}
    payment_link_id = link_data.get("id")

    if not payment_link_id:
        raise RuntimeError("Wompi did not return a payment link ID")

    payment_url = f"https://checkout.wompi.co/l/{payment_link_id}"

    return {
        "id": payment_link_id,
        "url": payment_url,
        "environment": environment,
        "amount_cop": amount_cop,
        "request": payload,
        "response": data,
    }



def get_transaction(transaction_id):
    """Get the current state of a Wompi transaction from the backend."""
    environment = _wompi_environment()
    private_key = _wompi_private_key()
    base_url = WOMPI_BASE_URLS[environment]

    transaction_id = str(transaction_id or "").strip()

    if not transaction_id:
        raise ValueError("Wompi transaction ID is required")

    response = requests.get(
        f"{base_url}/transactions/{transaction_id}",
        headers={
            "Authorization": f"Bearer {private_key}",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        try:
            error_data = response.json()
            error_message = (
                error_data.get("error", {}).get("message")
                or error_data.get("message")
                or response.text
            )
        except ValueError:
            error_message = response.text

        raise RuntimeError(
            f"Wompi transaction API error {response.status_code}: "
            f"{error_message}"
        )

    data = response.json()
    transaction = data.get("data") or {}

    if not transaction.get("id"):
        raise RuntimeError("Wompi did not return transaction data")

    return {
        "environment": environment,
        "transaction": transaction,
        "response": data,
    }
