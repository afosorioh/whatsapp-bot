import os
from datetime import timedelta

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
    ADVISOR_TEMPLATE_NAME = os.getenv(
        "ADVISOR_TEMPLATE_NAME",
        "notificacion_interna"
    )
    ADVISOR_TEMPLATE_LANGUAGE = os.getenv(
        "ADVISOR_TEMPLATE_LANGUAGE",
        "es"
    )

    ORDER_TEMPLATE_NAME = os.getenv(
        "ORDER_TEMPLATE_NAME",
        "notificacion_pedido"
    )
    ORDER_TEMPLATE_LANGUAGE = os.getenv(
        "ORDER_TEMPLATE_LANGUAGE",
        "es"
    )

    RESERVATION_TEMPLATE_NAME = os.getenv(
        "RESERVATION_TEMPLATE_NAME",
        "notificacion_reserva"
    )
    RESERVATION_TEMPLATE_LANGUAGE = os.getenv(
        "RESERVATION_TEMPLATE_LANGUAGE",
        "es"
    )

    PORTFOLIO_PDF_URL = os.getenv("PORTFOLIO_PDF_URL")
    CHATBOT_API_KEY = os.getenv("CHATBOT_API_KEY")
    TIMEZONE = os.getenv("TIMEZONE", "America/Bogota")
    CHATBOT_MAX_UPLOAD_MB = int(os.getenv("CHATBOT_MAX_UPLOAD_MB", "20"))
    MAX_CONTENT_LENGTH = CHATBOT_MAX_UPLOAD_MB * 1024 * 1024

    # Lightweight internal management inbox authentication.
    # The token is submitted once on the login page and then kept in the
    # signed Flask session cookie. Never expose the token in a URL.
    CHATBOT_ADMIN_TOKEN = os.getenv("CHATBOT_ADMIN_TOKEN")
    CHATBOT_MANAGEMENT_URL = os.getenv(
        "CHATBOT_MANAGEMENT_URL",
        "https://gestion.cervecerialibre.com/chatbot/gestion/"
    )

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE",
        "true"
    ).lower() in ("1", "true", "yes", "on")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{os.getenv('DB_USER')}:"
        f"{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}/"
        f"{os.getenv('DB_NAME')}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
