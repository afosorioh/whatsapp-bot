from app import create_app
from app.services.whatsapp_service import send_whatsapp_message

app = create_app()

with app.app_context():
    response = send_whatsapp_message(
        "+573006060492",
        "Prueba desde Flask hacia WhatsApp"
    )
    print(response)
