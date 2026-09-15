from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate


db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    migrate.init_app(app, db)

    from app.models import (
        Customer,
        Product,
        Conversation,
        Message,
        Order,
        OrderItem,
        Reservation,
        Payment,
        BarLocation,
    )

    from app.routes.webhook import webhook_bp
    app.register_blueprint(webhook_bp)

    from app.routes.products_api import products_api_bp
    app.register_blueprint(products_api_bp)

    from app.routes.management import management_bp
    app.register_blueprint(management_bp)

    from app.routes.management_inventory import management_inventory_bp
    app.register_blueprint(management_inventory_bp)

    return app
