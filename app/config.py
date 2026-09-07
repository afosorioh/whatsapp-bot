import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    WHATSAPP_GRAPH_VERSION = os.getenv("WHATSAPP_GRAPH_VERSION", "v23.0")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
    ADVISOR_WHATSAPP_NUMBER = os.getenv("ADVISOR_WHATSAPP_NUMBER")
    ADVISOR_TEMPLATE_NAME = os.getenv("ADVISOR_TEMPLATE_NAME", "notificacion_interna")
    ADVISOR_TEMPLATE_LANGUAGE = os.getenv("ADVISOR_TEMPLATE_LANGUAGE", "es")
    ORDER_TEMPLATE_NAME = os.getenv("ORDER_TEMPLATE_NAME", "notificacion_pedido")
    ORDER_TEMPLATE_LANGUAGE = os.getenv("ORDER_TEMPLATE_LANGUAGE", "es")
    RESERVATION_TEMPLATE_NAME = os.getenv("RESERVATION_TEMPLATE_NAME", "notificacion_reserva")
    RESERVATION_TEMPLATE_LANGUAGE = os.getenv("RESERVATION_TEMPLATE_LANGUAGE", "es")
    PORTFOLIO_PDF_URL = os.getenv("PORTFOLIO_PDF_URL")
    CHATBOT_API_KEY = os.getenv("CHATBOT_API_KEY")
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{os.getenv('DB_USER')}:"
        f"{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}/"
        f"{os.getenv('DB_NAME')}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
