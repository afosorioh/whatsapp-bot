from app import db
from app.models import Customer, Conversation, Message, Product
from pathlib import Path
import re
from decimal import Decimal
from flask import current_app
from app.services.whatsapp_service import (
    send_whatsapp_message,
    send_whatsapp_template,
    send_whatsapp_document,
    send_whatsapp_product_list,
    send_whatsapp_order_buttons,
    send_whatsapp_location_buttons
)

BASE_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = BASE_DIR / "content"

def get_customer_contact(context):
    customer_phone = context.get("customer_phone")
    customer_username = context.get("customer_username")

    if customer_phone:
        customer_phone = str(customer_phone).strip()

        if not customer_phone.startswith("+"):
            customer_phone = "+" + customer_phone

        return customer_phone

    if customer_username:
        customer_username = str(customer_username).strip()

        if not customer_username.startswith("@"):
            customer_username = "@" + customer_username

        return customer_username

    return "No disponible"

IDENTITY_CONTEXT_KEYS = (
    "customer_phone",
    "customer_username",
    "profile_name",
)


def reset_context_preserving_identity(context):
    """
    Limpia el estado funcional de una conversación sin perder los datos
    de contacto que Meta ya entregó.
    """
    context = dict(context or {})

    return {
        key: context[key]
        for key in IDENTITY_CONTEXT_KEYS
        if context.get(key)
    }


def reserve_order_stock(context):
    """
    Descuenta inventario de los productos del pedido.

    Retorna:
    - (True, None) si pudo descontar todo.
    - (False, mensaje_error) si algún producto no tiene stock suficiente.
    """
    items = context.get("items", [])

    if not items:
        return False, "No hay productos en el pedido."

    # Revalidar stock antes de descontar
    for item in items:
        product_id = item.get("product_id")
        quantity = Decimal(str(item.get("quantity")))

        product = Product.query.get(product_id)

        if not product or not product.active:
            return False, f"El producto {item.get('product_name')} ya no está disponible."

        current_stock = Decimal(str(product.stock_quantity or 0))

        if quantity > current_stock:
            return False, (
                f"No tenemos suficiente disponibilidad de {product.name}.\n"
                f"Disponible actual: {current_stock}."
            )

    # Descontar stock
    for item in items:
        product_id = item.get("product_id")
        quantity = Decimal(str(item.get("quantity")))

        product = Product.query.get(product_id)
        product.stock_quantity = Decimal(str(product.stock_quantity or 0)) - quantity

    return True, None

def get_available_products():
    return (
        Product.query
        .filter(
            Product.active.is_(True),
            Product.stock_quantity > 0
        )
        .order_by(Product.name)
        .all()
    )

def build_human_advisor_message(phone, incoming_text=None):
    return (
        "🔔 *Cliente solicita hablar con asesor*\n\n"
        f"*Cliente WhatsApp:* {phone}\n"
        "Motivo: solicitud directa desde el menú del chatbot.\n\n"
        "Por favor responder manualmente al cliente."
    )

def build_order_advisor_message(phone, context):
    items = context.get("items", [])
    customer_name = context.get("customer_name")
    delivery_address = context.get("delivery_address")
    delivery_time = context.get("delivery_time")

    lines = ["🔔 *Nuevo pedido desde el chatbot*\n"]

    lines.append(f"*Cliente WhatsApp:* {phone}")
    lines.append(f"*Nombre:* {customer_name}")
    lines.append(f"*Dirección y ciudad:* {delivery_address}")
    lines.append(f"*Rango de horario recepción:* {delivery_time}")

    lines.append("\n*Productos:*")

    total = Decimal("0")

    for item in items:
        quantity = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item["unit_price"]))
        line_total = quantity * unit_price
        total += line_total

        lines.append(
            f"- {item['product_name']} x {quantity} "
            f"= ${line_total:,.0f}"
        )

    lines.append(f"\n*Total estimado sin domicilio:* ${total:,.0f}")
    lines.append("\nEstado: pendiente de confirmar pago, envío y disponibilidad final.")

    return "\n".join(lines)

def build_order_products_text(context):
    items = context.get("items", [])
    lines = []
    total = Decimal("0")

    for item in items:
        quantity = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item["unit_price"]))
        line_total = quantity * unit_price
        total += line_total

        lines.append(
            f"{item['product_name']} x {quantity} = ${line_total:,.0f}"
        )

    products_text = " | ".join(lines)

    return products_text, total

def notify_order_template(phone, context):
    advisor_number = current_app.config.get("ADVISOR_WHATSAPP_NUMBER")
    template_name = current_app.config.get("ORDER_TEMPLATE_NAME")
    language_code = current_app.config.get("ORDER_TEMPLATE_LANGUAGE", "es")

    customer_name = context.get("customer_name") or "Cliente WhatsApp"
    customer_contact = get_customer_contact(context)
    delivery_address = context.get("delivery_address") or "-"
    delivery_time = context.get("delivery_time") or "-"

    products_text, total = build_order_products_text(context)
    total_text = f"${total:,.0f}"

    print("DEBUG notify_order_template()", flush=True)
    print("Advisor number:", advisor_number, flush=True)
    print("Template:", template_name, flush=True)
    print("Language:", language_code, flush=True)
    print("Customer:", customer_name, flush=True)
    print("Customer contact:", customer_contact, flush=True)
    print("Products:", products_text, flush=True)
    print("Address:", delivery_address, flush=True)
    print("Time:", delivery_time, flush=True)
    print("Total:", total_text, flush=True)

    if not advisor_number:
        print("ADVISOR_WHATSAPP_NUMBER no configurado", flush=True)
        return None

    response = send_whatsapp_template(
        advisor_number,
        template_name,
        language_code=language_code,
        parameters=[
            customer_name,
            customer_contact,
            products_text,
            delivery_address,
            delivery_time,
            total_text,
        ]
    )

    print("Order template response:", response, flush=True)
    return response


def build_reservation_advisor_message(phone, reservation_text):
    return (
        "🔔 *Nueva solicitud de reserva*\n\n"
        f"*Cliente WhatsApp:* {phone}\n\n"
        "*Datos enviados por el cliente:*\n"
        f"{reservation_text}\n\n"
        "Estado: pendiente de validación manual."
    )

def notify_advisor_template(
    customer_name,
    customer_contact,
    request_type,
    reference="-"
):
    advisor_number = current_app.config.get(
        "ADVISOR_WHATSAPP_NUMBER"
    )
    template_name = current_app.config.get(
        "ADVISOR_TEMPLATE_NAME"
    )
    language_code = current_app.config.get(
        "ADVISOR_TEMPLATE_LANGUAGE",
        "es"
    )

    customer_name = (
        str(customer_name).strip()
        if customer_name
        else "Cliente WhatsApp"
    )

    customer_contact = (
        str(customer_contact).strip()
        if customer_contact
        else "No disponible"
    )

    request_type = (
        str(request_type).strip()
        if request_type
        else "Solicitud"
    )

    reference = (
        str(reference).strip()
        if reference
        else "-"
    )

    print(
        "DEBUG notify_advisor_template()",
        flush=True
    )
    print(
        "Advisor number:",
        advisor_number,
        flush=True
    )
    print(
        "Template:",
        template_name,
        flush=True
    )
    print(
        "Language:",
        language_code,
        flush=True
    )
    print(
        "Customer:",
        customer_name,
        flush=True
    )
    print(
        "Customer contact:",
        customer_contact,
        flush=True
    )
    print(
        "Type:",
        request_type,
        flush=True
    )
    print(
        "Reference:",
        reference,
        flush=True
    )

    if not advisor_number:
        print(
            "ADVISOR_WHATSAPP_NUMBER no configurado",
            flush=True
        )
        return None

    if not template_name:
        print(
            "ADVISOR_TEMPLATE_NAME no configurado",
            flush=True
        )
        return None

    response = send_whatsapp_template(
        advisor_number,
        template_name,
        language_code=language_code,
        parameters=[
            customer_name,
            customer_contact,
            request_type,
            reference
        ]
    )

    print(
        "Advisor template response:",
        response,
        flush=True
    )

    return response

def notify_reservation_template(phone, context):
    advisor_number = current_app.config.get("ADVISOR_WHATSAPP_NUMBER")
    template_name = current_app.config.get("RESERVATION_TEMPLATE_NAME")
    language_code = current_app.config.get(
        "RESERVATION_TEMPLATE_LANGUAGE",
        "es"
    )

    customer_name = (
        context.get("reservation_name")
        or context.get("profile_name")
        or "Cliente WhatsApp"
    )
    customer_contact = get_customer_contact(context)
    location = context.get("reservation_location") or "-"
    date = context.get("reservation_date") or "-"
    time = context.get("reservation_time") or "-"
    people = context.get("reservation_people") or "-"

    print("DEBUG notify_reservation_template()", flush=True)
    print("Advisor number:", advisor_number, flush=True)
    print("Template:", template_name, flush=True)
    print("Language:", language_code, flush=True)
    print("Customer:", customer_name, flush=True)
    print("Customer contact:", customer_contact, flush=True)
    print("Location:", location, flush=True)
    print("Date:", date, flush=True)
    print("Time:", time, flush=True)
    print("People:", people, flush=True)

    if not advisor_number:
        print("ADVISOR_WHATSAPP_NUMBER no configurado", flush=True)
        return None

    response = send_whatsapp_template(
        advisor_number,
        template_name,
        language_code=language_code,
        parameters=[
            customer_name,
            customer_contact,
            location,
            date,
            time,
            people,
        ]
    )

    print("Reservation template response:", response, flush=True)
    return response


def build_reservation_summary(context):
    return (
        "🍺 *Solicitud de reserva recibida*\n\n"
        f"*Sede:* {context.get('reservation_location')}\n"
        f"*Fecha:* {context.get('reservation_date')}\n"
        f"*Hora:* {context.get('reservation_time')}\n"
        f"*Nombre:* {context.get('reservation_name')}\n"
        f"*Personas:* {context.get('reservation_people')}\n\n"
        "Un asesor validará disponibilidad y te confirmará por WhatsApp."
    )

def read_content_file(filename):
    file_path = CONTENT_DIR / filename

    try:
        return file_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "La información solicitada no está disponible en este momento. "
            "Te comunicaremos con un asesor."
        )

def build_order_summary(context):
    items = context.get("items", [])
    customer_name = context.get("customer_name")
    delivery_address = context.get("delivery_address")
    delivery_time = context.get("delivery_time")

    lines = ["🧾 *Resumen del pedido:*\n"]

    total = Decimal("0")

    for item in items:
        line_total = Decimal(str(item["unit_price"])) * Decimal(str(item["quantity"]))
        total += line_total

        lines.append(
            f"- {item['product_name']} x {item['quantity']} "
            f"= ${line_total:,.0f}"
        )

    lines.append(f"\n*Total estimado (no incluye domicilio):* ${total:,.0f}")

    lines.append("\n*Datos de entrega:*")
    lines.append(f"Nombre: {customer_name}")
    lines.append(f"Dirección: {delivery_address}")
    lines.append(f"Rango de horario de recepción: {delivery_time}")

    lines.append(
        "\nUn asesor continuará la atención para confirmar disponibilidad final, "
        "forma de pago y despacho."
    )

    return "\n".join(lines)

def get_or_create_customer(identifier, customer_phone=None):
    customer = Customer.query.filter_by(
        whatsapp_number=identifier
    ).first()

    if not customer:
        customer = Customer(
            whatsapp_number=identifier,
            phone=customer_phone or (
                identifier
                if not str(identifier).startswith("CO.")
                else None
            )
        )
        db.session.add(customer)
        db.session.commit()

    elif customer_phone and customer.phone != customer_phone:
        customer.phone = customer_phone
        db.session.commit()

    return customer


def get_or_create_conversation(customer):
    conversation = Conversation.query.filter_by(
        customer_id=customer.id,
        human_handoff=False
    ).first()

    if not conversation:
        conversation = Conversation(
            customer_id=customer.id,
            whatsapp_number=customer.whatsapp_number,
            current_state="MAIN_MENU",
            context={}
        )
        db.session.add(conversation)
        db.session.commit()

    return conversation


def save_message(conversation, direction, content, raw_payload=None):
    message = Message(
        conversation_id=conversation.id,
        direction=direction,
        message_type="text",
        content=content,
        raw_payload=raw_payload or {}
    )
    db.session.add(message)
    db.session.commit()

def build_products_message():
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    if not products:
        return (
            "Por ahora no tengo productos cargados en el sistema. "
            "Te comunico con un asesor."
        )

    lines = ["🍺 *Cervezas disponibles:*\n"]

    for idx, product in enumerate(products, start=1):
        stock = product.stock_quantity or 0
        lines.append(
            f"{idx}. *{product.name}* - {product.presentation or ''}\n"
            f"   Precio: ${product.price:,.0f}\n"
            f"   Disponible: {stock}\n"
        )

    lines.append(
        "Para hacer tu pedido, responde con el número del producto y la cantidad.\n\n"
        "Ejemplo:\n"
        "1 x 6\n"
        "2 x 3\n\n"
        "O escribe *menu* para volver al menú principal."
    )

    return "\n".join(lines)

def main_menu():
    return (
        "Hola, soy el asistente de Cervecería Libre 🍺\n\n"
        "Elige una opción:\n"
        "1. Horarios bares\n"
        "2. Reservas\n"
        "3. Productos y pedidos\n"
        "4. Portafolio\n"
        "5. Hablar con asesor"
    )


def process_incoming_message(
    phone,
    text,
    customer_phone=None,
    customer_username=None,
    profile_name=None
):
    # "phone" es el identificador técnico de la conversación.
    # Puede ser un teléfono o un BSUID CO.xxxxx.
    if not customer_phone and phone and not str(phone).startswith("CO."):
        digits = "".join(ch for ch in str(phone) if ch.isdigit())
        if 8 <= len(digits) <= 15:
            customer_phone = digits

    customer = get_or_create_customer(
        phone,
        customer_phone=customer_phone
    )
    conversation = get_or_create_conversation(customer)

    context = dict(conversation.context or {})

    if customer_phone:
        context["customer_phone"] = str(customer_phone).strip()

    if customer_username:
        context["customer_username"] = str(customer_username).strip()

    if profile_name:
        context["profile_name"] = str(profile_name).strip()

    conversation.context = context
    db.session.commit()

    print(
        "DEBUG customer identity:",
        {
            "recipient": phone,
            "customer_phone": context.get("customer_phone"),
            "customer_username": context.get("customer_username"),
            "profile_name": context.get("profile_name"),
        },
        flush=True
    )

    incoming_text = text.strip()
    save_message(conversation, "inbound", incoming_text)

    normalized = incoming_text.lower()

    if normalized in ["menu", "menú", "inicio", "cancelar"]:
        conversation.current_state = "MAIN_MENU"
        conversation.context = reset_context_preserving_identity(
            conversation.context
        )
        conversation.human_handoff = False
        db.session.commit()

        reply = main_menu()
        save_message(conversation, "outbound", reply)
        return reply

    if conversation.current_state == "WAITING_PRODUCT_SELECTION":
        if not normalized.startswith("product_"):
            reply = "Por favor selecciona una cerveza desde la lista enviada."
            save_message(conversation, "outbound", reply)
            return reply

        product_id = int(normalized.replace("product_", ""))

        product = Product.query.get(product_id)

        if not product or not product.active:
            reply = "Ese producto ya no está disponible. Escribe *3* para ver la lista actualizada."
            save_message(conversation, "outbound", reply)
            return reply

        context = dict(conversation.context or {})
        context["selected_product_id"] = product.id
        context["selected_product_name"] = product.name
        context["selected_product_price"] = str(product.price)
        context["selected_product_stock"] = str(product.stock_quantity or 0)
        conversation.context = context
        conversation.current_state = "WAITING_SELECTED_PRODUCT_QUANTITY"
        db.session.commit()

        reply = (
            f"Seleccionaste *{product.name}*.\n"
            f"Precio: ${product.price:,.0f}\n"
            f"Disponible: {product.stock_quantity}\n\n"
            "¿Cuántas unidades deseas?"
        )
        save_message(conversation, "outbound", reply)
        return reply


    if conversation.current_state == "WAITING_SELECTED_PRODUCT_QUANTITY":
        try:
            quantity = Decimal(incoming_text.replace(",", "."))
        except Exception:
            reply = "Por favor escribe solo la cantidad. Ejemplo: 6"
            save_message(conversation, "outbound", reply)
            return reply

        if quantity <= 0:
            reply = "La cantidad debe ser mayor que cero."
            save_message(conversation, "outbound", reply)
            return reply

        context = dict(conversation.context or {})
        product_id = context.get("selected_product_id")

        product = Product.query.get(product_id)

        if not product or not product.active:
            reply = "El producto seleccionado ya no está disponible. Escribe *3* para iniciar de nuevo."
            save_message(conversation, "outbound", reply)
            return reply

        if quantity > product.stock_quantity:
            context = dict(conversation.context or {})

            # Limpiar selección actual
            context.pop("selected_product_id", None)
            context.pop("selected_product_name", None)
            context.pop("selected_product_price", None)
            context.pop("selected_product_stock", None)

            conversation.context = context
            conversation.current_state = "WAITING_PRODUCT_SELECTION"
            db.session.commit()

            # Volver a consultar productos disponibles
            products = get_available_products()

            if products:
                send_whatsapp_product_list(phone, products)

            reply = (
                f"No tenemos suficiente disponibilidad de *{product.name}*.\n"
                f"Disponible actual: {product.stock_quantity}.\n\n"
                "Te envié nuevamente la lista de cervezas para que puedas "
                "seleccionar otro producto o volver a escoger éste con una "
                "cantidad menor."
            )

            save_message(conversation, "outbound", reply)
            return reply

        items = context.get("items", [])

        items.append({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": str(quantity),
            "unit_price": str(product.price)
        })

        context["items"] = items
        context.pop("selected_product_id", None)
        context.pop("selected_product_name", None)
        context.pop("selected_product_price", None)
        context.pop("selected_product_stock", None)

        conversation.context = context
        conversation.current_state = "WAITING_ADD_MORE_OR_FINISH"
        db.session.commit()

        send_whatsapp_order_buttons(phone)

        reply = "Producto agregado al pedido ✅"
        save_message(conversation, "outbound", reply)
        return reply


    if conversation.current_state == "WAITING_ADD_MORE_OR_FINISH":
        if normalized == "add_more_product":
            products = get_available_products()
            send_whatsapp_product_list(phone, products)

            conversation.current_state = "WAITING_PRODUCT_SELECTION"
            db.session.commit()

            reply = "Selecciona otra cerveza de la lista 🍺"
            save_message(conversation, "outbound", reply)
            return reply

        if normalized == "finish_order":
            conversation.current_state = "WAITING_CUSTOMER_NAME"
            db.session.commit()

            reply = "Perfecto. Ahora por favor indícame tu *nombre completo*."
            save_message(conversation, "outbound", reply)
            return reply

        reply = "Por favor selecciona *Agregar otra* o *Finalizar*."
        save_message(conversation, "outbound", reply)
        return reply

    if conversation.current_state == "WAITING_CUSTOMER_NAME":
        context = dict(conversation.context or {})
        context["customer_name"] = incoming_text
        conversation.context = context
        conversation.current_state = "WAITING_DELIVERY_ADDRESS"
        db.session.commit()

        reply = "Gracias. Ahora indícame la *dirección y ciudad de entrega*."
        save_message(conversation, "outbound", reply)
        return reply

    if conversation.current_state == "WAITING_DELIVERY_ADDRESS":
        context = dict(conversation.context or {})
        context["delivery_address"] = incoming_text
        conversation.context = context
        conversation.current_state = "WAITING_DELIVERY_TIME"
        db.session.commit()

        reply = "Perfecto. ¿En qué *día y rango de horario puedes recibir el pedido*?"
        save_message(conversation, "outbound", reply)
        return reply

    if conversation.current_state == "WAITING_DELIVERY_TIME":
        context = dict(conversation.context or {})
        context["delivery_time"] = incoming_text
        conversation.context = context

        stock_ok, stock_error = reserve_order_stock(context)

        if not stock_ok:
            db.session.rollback()

            reply = (
                "Lo siento, mientras completábamos el pedido cambió la disponibilidad.\n\n"
                f"{stock_error}\n\n"
                "Por favor escribe *3* para revisar nuevamente los productos disponibles."
            )

            conversation.current_state = "MAIN_MENU"
            conversation.context = reset_context_preserving_identity(
                conversation.context
            )
            conversation.human_handoff = False
            db.session.commit()

            save_message(conversation, "outbound", reply)
            return reply

        try:
            notify_order_template(phone, context)
        except Exception as e:
            print(f"Error enviando pedido al asesor: {e}", flush=True)

        reply = build_order_summary(context)

        conversation.current_state = "HUMAN_HANDOFF"
        conversation.human_handoff = True
        db.session.commit()

        save_message(conversation, "outbound", reply)
        return reply

    if conversation.current_state == "WAITING_RESERVATION_DATA":
        context = dict(conversation.context or {})
        context["reservation_data"] = incoming_text
        conversation.context = context

        try:
            notify_advisor_template(
                customer_name=(
                    context.get("profile_name")
                    or "Cliente WhatsApp"
                ),
                customer_contact=get_customer_contact(context),
                request_type="Reserva",
                reference="-"
            )
        except Exception as e:
            print(f"Error enviando reserva al asesor: {e}", flush=True)

        reply = (
            "Gracias 🍺\n\n"
            "Hemos recibido tu solicitud de reserva. "
            "Un asesor revisará la disponibilidad y te confirmará por WhatsApp."
        )

        conversation.current_state = "HUMAN_HANDOFF"
        conversation.human_handoff = True

        db.session.commit()
        save_message(conversation, "outbound", reply)

        return reply

    if conversation.current_state == "WAITING_RESERVATION_LOCATION":
        context = dict(conversation.context or {})

        if normalized == "reservation_location_barrio":
            context["reservation_location"] = "Barrio Colombia"
        elif normalized == "reservation_location_mercado":
            context["reservation_location"] = "Mercado del Río"
        else:
            reply = "Por favor selecciona una sede usando los botones enviados."
            save_message(conversation, "outbound", reply)
            return reply

        conversation.context = context
        conversation.current_state = "WAITING_RESERVATION_DATE"
        db.session.commit()

        reply = "Perfecto. ¿Para qué *fecha* quieres la reserva? Ejemplo: viernes 7 de junio"
        save_message(conversation, "outbound", reply)
        return reply


    if conversation.current_state == "WAITING_RESERVATION_DATE":
        context = dict(conversation.context or {})
        context["reservation_date"] = incoming_text
        conversation.context = context
        conversation.current_state = "WAITING_RESERVATION_TIME"
        db.session.commit()

        reply = "Gracias. ¿A qué *hora* deseas reservar? Ejemplo: 8:00 p.m."
        save_message(conversation, "outbound", reply)
        return reply


    if conversation.current_state == "WAITING_RESERVATION_TIME":
        context = dict(conversation.context or {})
        context["reservation_time"] = incoming_text
        conversation.context = context
        conversation.current_state = "WAITING_RESERVATION_NAME"
        db.session.commit()

        reply = "Perfecto. Indícame el *nombre* para la reserva."
        save_message(conversation, "outbound", reply)
        return reply


    if conversation.current_state == "WAITING_RESERVATION_NAME":
        context = dict(conversation.context or {})
        context["reservation_name"] = incoming_text
        conversation.context = context
        conversation.current_state = "WAITING_RESERVATION_PEOPLE"
        db.session.commit()

        reply = "Gracias. ¿Para cuántas *personas* es la reserva?"
        save_message(conversation, "outbound", reply)
        return reply


    if conversation.current_state == "WAITING_RESERVATION_PEOPLE":
        people = incoming_text.strip()

        if not people.isdigit() or int(people) <= 0:
            reply = "Por favor escribe solo el número de personas. Ejemplo: 4"
            save_message(conversation, "outbound", reply)
            return reply

        context = dict(conversation.context or {})
        context["reservation_people"] = people
        conversation.context = context

        try:
            notify_reservation_template(phone, context)
        except Exception as e:
            print(f"Error enviando reserva al asesor: {e}", flush=True)

        reply = build_reservation_summary(context)

        conversation.current_state = "HUMAN_HANDOFF"
        conversation.human_handoff = True
        db.session.commit()

        save_message(conversation, "outbound", reply)
        return reply

    elif normalized == "1":
        reply = read_content_file("horarios.txt")
        conversation.current_state = "MAIN_MENU"

    elif normalized == "2":
        context = dict(conversation.context or {})
        context["reservation"] = {}
        conversation.context = context

        send_whatsapp_location_buttons(phone)

        reply = "Iniciemos tu reserva 🍺"
        conversation.current_state = "WAITING_RESERVATION_LOCATION"
        conversation.human_handoff = False

    elif normalized == "3":
        products = get_available_products()

        if not products:
            reply = (
                "Por ahora no tengo productos cargados en el sistema. "
                "Te comunico con un asesor."
            )
        else:
            send_whatsapp_product_list(phone, products)
            reply = "Te envié la lista de cervezas disponibles 🍺"

            context = dict(conversation.context or {})
            context["items"] = []
            conversation.context = context
            conversation.current_state = "WAITING_PRODUCT_SELECTION"

    elif normalized == "4":
        pdf_url = current_app.config.get("PORTFOLIO_PDF_URL")

        try:
            send_whatsapp_document(
                phone,
                pdf_url,
                filename="portafolio_cerveceria_libre.pdf",
                caption="🍺 Te compartimos nuestro portafolio de Cervecería Libre."
            )

            reply = (
                "Listo 🍺\n\n"
                "Te envié nuestro portafolio en PDF. "
                "Escribe *menu* para volver al menú principal."
            )

        except Exception as e:
            print(f"Error enviando portafolio PDF: {e}")
            reply = (
                "No pude enviarte el portafolio en este momento. "
                "Por favor intenta más tarde o escribe *5* para hablar con un asesor."
            )

        conversation.current_state = "MAIN_MENU"

    elif normalized == "5":
        context = dict(conversation.context or {})

        customer_name = (
            context.get("profile_name")
            or "Cliente WhatsApp"
        )

        customer_contact = get_customer_contact(
            context
        )
        try:
            notify_advisor_template(
                customer_name=customer_name,
                customer_contact=customer_contact,
                request_type="Solicitud de asesor",
                reference="-"
            )
        except Exception as e:
            print(
                f"Error enviando solicitud de asesor: {e}",
                flush=True
            )

        reply = (
            "Perfecto 🍺\n\n"
            "Ya notificamos a un asesor para que continúe la atención. "
            "Te responderemos por WhatsApp en breve."
        )

        conversation.current_state = "HUMAN_HANDOFF"
        conversation.human_handoff = True

    else:
        reply = main_menu()

    db.session.commit()
    save_message(conversation, "outbound", reply)

    return reply
