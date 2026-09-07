from app import create_app
from flask import current_app
from app.services.whatsapp_service import send_whatsapp_message

app = create_app()

with app.app_context():
    advisor = current_app.config.get("ADVISOR_WHATSAPP_NUMBER")
    print("Advisor:", advisor)

    response = send_whatsapp_message(
        advisor,
        "Prueba directa al asesor desde el bot."
    )

    print(response)
