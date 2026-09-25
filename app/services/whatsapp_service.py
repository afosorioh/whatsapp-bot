import requests
from flask import current_app


def download_whatsapp_media(media_id):
    """
    Download inbound WhatsApp media through the Graph API.

    Meta first returns a short-lived download URL for the media ID. The
    binary request must also be authenticated with the WhatsApp access token.
    Files are not made public or persisted by this helper.
    """
    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    graph_version = current_app.config.get("WHATSAPP_GRAPH_VERSION", "v23.0")

    if not access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")

    media_id = str(media_id).strip()
    metadata_url = (
        f"https://graph.facebook.com/{graph_version}/{media_id}"
    )
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    metadata_response = requests.get(
        metadata_url,
        headers=headers,
        timeout=20
    )
    metadata_response.raise_for_status()
    metadata = metadata_response.json()

    download_url = metadata.get("url")
    if not download_url:
        raise RuntimeError("WhatsApp media URL was not returned by Meta")

    media_response = requests.get(
        download_url,
        headers=headers,
        timeout=30
    )
    media_response.raise_for_status()

    return {
        "content": media_response.content,
        "mime_type": (
            metadata.get("mime_type")
            or media_response.headers.get("Content-Type")
            or "application/octet-stream"
        ),
        "file_size": metadata.get("file_size"),
        "sha256": metadata.get("sha256"),
    }

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



def _whatsapp_api_context():
    access_token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    graph_version = current_app.config.get("WHATSAPP_GRAPH_VERSION", "v23.0")

    if not access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")

    if not phone_number_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID is not configured")

    return access_token, phone_number_id, graph_version


def send_whatsapp_media_file(to, file_storage, media_type, caption=None):
    """Upload an image/document to Meta and send it to the recipient."""
    if media_type not in {"image", "document"}:
        raise ValueError("Only image and document attachments are supported")

    access_token, phone_number_id, graph_version = _whatsapp_api_context()

    filename = (file_storage.filename or "attachment").strip() or "attachment"
    mime_type = file_storage.mimetype or "application/octet-stream"

    upload_url = (
        f"https://graph.facebook.com/"
        f"{graph_version}/{phone_number_id}/media"
    )

    file_storage.stream.seek(0)

    upload_response = requests.post(
        upload_url,
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "messaging_product": "whatsapp",
            "type": mime_type,
        },
        files={
            "file": (
                filename,
                file_storage.stream,
                mime_type,
            )
        },
        timeout=60,
    )

    if upload_response.status_code >= 400:
        print(
            "WhatsApp API media upload error:",
            upload_response.status_code,
            upload_response.text,
            flush=True,
        )

    upload_response.raise_for_status()
    upload_data = upload_response.json()
    media_id = upload_data.get("id")

    if not media_id:
        raise RuntimeError("Meta did not return a media ID after upload")

    recipient_fields = build_recipient_fields(to)
    media_payload = {"id": media_id}

    if caption:
        media_payload["caption"] = str(caption).strip()

    if media_type == "document":
        media_payload["filename"] = filename

    message_url = (
        f"https://graph.facebook.com/"
        f"{graph_version}/{phone_number_id}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": media_type,
        media_type: media_payload,
    }

    response = requests.post(
        message_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        print(
            "WhatsApp API media message error:",
            response.status_code,
            response.text,
            flush=True,
        )

    response.raise_for_status()

    return {
        "response": response.json(),
        "media_id": media_id,
        "message_type": media_type,
        "filename": filename,
        "mime_type": mime_type,
        "caption": str(caption or "").strip(),
    }


def send_whatsapp_contact(to, name, phone, email=None):
    """Send a WhatsApp contact card to the recipient."""
    access_token, phone_number_id, graph_version = _whatsapp_api_context()

    name = str(name or "").strip()
    phone = str(phone or "").strip()
    email = str(email or "").strip()

    if not name:
        raise ValueError("Contact name is required")

    if not phone:
        raise ValueError("Contact phone is required")

    clean_phone = (
        phone.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    # Meta requires formatted_name plus at least one additional name field
    # (for example first_name or last_name) in outbound contact messages.
    # Split the entered/displayed name conservatively: the first token becomes
    # first_name and the remaining tokens become last_name.
    name_parts = name.split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None

    contact_name = {
        "formatted_name": name,
        "first_name": first_name,
    }

    if last_name:
        contact_name["last_name"] = last_name

    contact = {
        "name": contact_name,
        "phones": [
            {
                "phone": clean_phone,
                "type": "WORK",
            }
        ],
    }

    if email:
        contact["emails"] = [
            {
                "email": email,
                "type": "WORK",
            }
        ]

    recipient_fields = build_recipient_fields(to)
    payload = {
        "messaging_product": "whatsapp",
        **recipient_fields,
        "type": "contacts",
        "contacts": [contact],
    }

    url = (
        f"https://graph.facebook.com/"
        f"{graph_version}/{phone_number_id}/messages"
    )

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code >= 400:
        print(
            "WhatsApp API contact error:",
            response.status_code,
            response.text,
            flush=True,
        )

        try:
            error_data = response.json()
            error_message = (
                error_data.get("error", {}).get("message")
                or response.text
            )
        except ValueError:
            error_message = response.text

        raise RuntimeError(
            f"WhatsApp contact API error {response.status_code}: "
            f"{error_message}"
        )

    return {
        "response": response.json(),
        "contact": contact,
    }
