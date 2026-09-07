import requests
from flask import current_app

def build_recipient_fields(recipient):
    recipient = str(recipient).strip()

    # Business-Scoped User ID
    if recipient.startswith("CO."):
        return {
            "recipient": recipient
        }

    # Número telefónico
    phone = recipient
    phone = phone.replace(" ", "")
    phone = phone.replace("-", "")
    phone = phone.replace("(", "")
    phone = phone.replace(")", "")

    if not phone.startswith("+"):
        phone = "+" + phone

    return {
        "to": phone
    }

def send_whatsapp_message(to, text):
    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get("WHATSAPP_GRAPH_VERSION", "v23.0")

    url = (
        f"https://graph.facebook.com/"
        f"{graph_version}/{phone_number_id}/messages"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    recipient_fields = build_recipient_fields(to)

    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": "text",
        "text": {
            "body": text
        }
    }

    print(
        "WHATSAPP OUTGOING PAYLOAD:",
        payload,
        flush=True
    )

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        print(
            "WhatsApp API error:",
            response.status_code,
            response.text,
            flush=True
        )

    response.raise_for_status()
    return response.json()

def send_whatsapp_location_buttons(to):
    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get(
        "WHATSAPP_GRAPH_VERSION",
        "v23.0"
    )

    url = (
        f"https://graph.facebook.com/"
        f"{graph_version}/{phone_number_id}/messages"
    )

    recipient_fields = build_recipient_fields(to)

    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "¿En cuál sede deseas reservar?"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "reservation_location_barrio",
                            "title": "Barrio Colombia"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "reservation_location_mercado",
                            "title": "Mercado del Río"
                        }
                    }
                ]
            }
        }
    }

    print(
        "WHATSAPP LOCATION BUTTONS PAYLOAD:",
        payload,
        flush=True
    )

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        print(
            "WhatsApp API location buttons error:",
            response.status_code,
            response.text,
            flush=True
        )

    response.raise_for_status()

    return response.json()

def send_whatsapp_template(
    to,
    template_name,
    language_code="es",
    parameters=None
):
    to = normalize_phone_number(to)

    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get("WHATSAPP_GRAPH_VERSION", "v23.0")

    url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"

    components = []

    if parameters:
        components.append({
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": str(value)
                }
                for value in parameters
            ]
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
		"policy": "deterministic",
                "code": language_code
            },
            "components": components
        }
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        print(
            "WhatsApp API template error:",
            response.status_code,
            response.text,
            flush=True
        )

    response.raise_for_status()
    return response.json()

def send_whatsapp_product_list(to, products):
    recipient_fields = build_recipient_fields(to)

    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get("WHATSAPP_GRAPH_VERSION", "v23.0")

    url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"

    rows = []

    for product in products[:10]:
        rows.append({
            "id": f"product_{product.id}",
            "title": product.name[:24],
            "description": f"{product.presentation or ''} - ${product.price:,.0f}"[:72]
        })

    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": "Cervezas disponibles"
            },
            "body": {
                "text": "Selecciona la cerveza que quieres pedir:"
            },
            "footer": {
                "text": "Cervecería Libre"
            },
            "action": {
                "button": "Ver cervezas",
                "sections": [
                    {
                        "title": "Productos",
                        "rows": rows
                    }
                ]
            }
        }
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        print("WhatsApp API list error:", response.status_code, response.text)

    response.raise_for_status()
    return response.json()


def send_whatsapp_order_buttons(to):
    recipient_fields = build_recipient_fields(to)

    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get("WHATSAPP_GRAPH_VERSION", "v23.0")

    url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "¿Quieres agregar otra cerveza o finalizar el pedido?"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "add_more_product",
                            "title": "Agregar otra"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "finish_order",
                            "title": "Finalizar"
                        }
                    }
                ]
            }
        }
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        print("WhatsApp API button error:", response.status_code, response.text)

    response.raise_for_status()
    return response.json()

def normalize_phone_number(phone):
    phone = str(phone).strip()
    phone = phone.replace(" ", "")
    phone = phone.replace("-", "")
    phone = phone.replace("(", "")
    phone = phone.replace(")", "")

    if not phone.startswith("+"):
        phone = "+" + phone

    return phone

def send_whatsapp_document(
    to,
    document_url,
    filename="portafolio.pdf",
    caption=None
):
    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get(
        "WHATSAPP_GRAPH_VERSION",
        "v23.0"
    )

    url = (
        f"https://graph.facebook.com/"
        f"{graph_version}/{phone_number_id}/messages"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    recipient_fields = build_recipient_fields(to)

    document_payload = {
        "link": document_url,
        "filename": filename
    }

    if caption:
        document_payload["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": "document",
        "document": document_payload
    }

    print(
        "WHATSAPP DOCUMENT PAYLOAD:",
        payload,
        flush=True
    )

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        print(
            "WhatsApp API document error:",
            response.status_code,
            response.text,
            flush=True
        )

    response.raise_for_status()
    return response.json()
