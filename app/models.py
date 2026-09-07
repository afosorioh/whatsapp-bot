from datetime import datetime
from app import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)

    whatsapp_number = db.Column(db.String(30), unique=True, nullable=False)

    name = db.Column(db.String(150))
    document_type = db.Column(db.String(20))
    document_number = db.Column(db.String(50))

    email = db.Column(db.String(150))
    phone = db.Column(db.String(30))

    address = db.Column(db.Text)

    siigo_customer_id = db.Column(db.String(100))
    siigo_synced = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)

    external_id = db.Column(db.String(100))

    name = db.Column(db.String(150), nullable=False)

    style = db.Column(db.String(100))

    description = db.Column(db.Text)

    presentation = db.Column(db.String(50))

    volume_ml = db.Column(db.Integer)

    price = db.Column(db.Numeric(12, 2), nullable=False)

    stock_quantity = db.Column(db.Numeric(12, 2), default=0)

    active = db.Column(db.Boolean, default=True)

    source = db.Column(db.String(50), default="local")

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id")
    )

    whatsapp_number = db.Column(
        db.String(30),
        nullable=False
    )

    current_state = db.Column(
        db.String(50),
        default="MAIN_MENU"
    )

    last_option = db.Column(db.String(50))

    human_handoff = db.Column(
        db.Boolean,
        default=False
    )

    context = db.Column(db.JSON)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id")
    )

    whatsapp_message_id = db.Column(db.String(150))

    direction = db.Column(
        db.String(20),
        nullable=False
    )

    message_type = db.Column(db.String(30))

    content = db.Column(db.Text)

    raw_payload = db.Column(db.JSON)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id")
    )

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id")
    )

    status = db.Column(
        db.String(50),
        default="DRAFT"
    )

    subtotal = db.Column(
        db.Numeric(12, 2),
        default=0
    )

    delivery_fee = db.Column(
        db.Numeric(12, 2),
        default=0
    )

    total = db.Column(
        db.Numeric(12, 2),
        default=0
    )

    delivery_address = db.Column(db.Text)

    notes = db.Column(db.Text)

    assigned_to_advisor = db.Column(
        db.Boolean,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE")
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id")
    )

    product_name = db.Column(
        db.String(150),
        nullable=False
    )

    quantity = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    unit_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    total = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )


class BarLocation(db.Model):
    __tablename__ = "bar_locations"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(150),
        nullable=False
    )

    address = db.Column(db.Text)

    phone = db.Column(db.String(30))

    opening_hours = db.Column(db.Text)

    active = db.Column(
        db.Boolean,
        default=True
    )


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id")
    )

    location_id = db.Column(
        db.Integer,
        db.ForeignKey("bar_locations.id")
    )

    reservation_date = db.Column(
        db.Date,
        nullable=False
    )

    reservation_time = db.Column(
        db.Time,
        nullable=False
    )

    people_count = db.Column(
        db.Integer,
        nullable=False
    )

    status = db.Column(
        db.String(50),
        default="REQUESTED"
    )

    notes = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id")
    )

    provider = db.Column(
        db.String(50),
        default="wompi"
    )

    reference = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    payment_url = db.Column(db.Text)

    qr_url = db.Column(db.Text)

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    currency = db.Column(
        db.String(10),
        default="COP"
    )

    status = db.Column(
        db.String(50),
        default="PENDING"
    )

    provider_transaction_id = db.Column(db.String(150))

    raw_payload = db.Column(db.JSON)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
