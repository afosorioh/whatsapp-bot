from flask import Blueprint, request, jsonify
from decimal import Decimal, InvalidOperation
from app import db
from app.models import Product
from app.services.auth_service import require_api_key


products_api_bp = Blueprint(
    "products_api",
    __name__,
    url_prefix="/chatbot/api"
)


def product_to_dict(product):
    return {
        "id": product.id,
        "external_id": product.external_id,
        "name": product.name,
        "style": product.style,
        "description": product.description,
        "presentation": product.presentation,
        "volume_ml": product.volume_ml,
        "price": float(product.price or 0),
        "stock_quantity": float(product.stock_quantity or 0),
        "active": product.active,
        "source": product.source,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None
    }


def parse_decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} must be numeric")


@products_api_bp.route("/products", methods=["GET"])
@require_api_key
def list_products():
    active = request.args.get("active")

    query = Product.query.order_by(Product.name)

    if active is not None:
        if active.lower() in ["true", "1", "yes"]:
            query = query.filter_by(active=True)
        elif active.lower() in ["false", "0", "no"]:
            query = query.filter_by(active=False)

    products = query.all()

    return jsonify({
        "items": [product_to_dict(product) for product in products],
        "count": len(products)
    })


@products_api_bp.route("/products/<int:product_id>", methods=["GET"])
@require_api_key
def get_product(product_id):
    product = Product.query.get_or_404(product_id)

    return jsonify(product_to_dict(product))


@products_api_bp.route("/products", methods=["POST"])
@require_api_key
def create_product():
    data = request.get_json() or {}

    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400

    if data.get("price") is None:
        return jsonify({"error": "price is required"}), 400

    try:
        price = parse_decimal(data.get("price"), "price")
        stock_quantity = parse_decimal(data.get("stock_quantity", 0), "stock_quantity")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    product = Product(
        external_id=data.get("external_id"),
        name=data.get("name"),
        style=data.get("style"),
        description=data.get("description"),
        presentation=data.get("presentation"),
        volume_ml=data.get("volume_ml"),
        price=price,
        stock_quantity=stock_quantity,
        active=data.get("active", True),
        source=data.get("source", "api")
    )

    db.session.add(product)
    db.session.commit()

    return jsonify(product_to_dict(product)), 201


@products_api_bp.route("/products/<int:product_id>", methods=["PUT"])
@require_api_key
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json() or {}

    if "name" in data:
        product.name = data.get("name")

    if "external_id" in data:
        product.external_id = data.get("external_id")

    if "style" in data:
        product.style = data.get("style")

    if "description" in data:
        product.description = data.get("description")

    if "presentation" in data:
        product.presentation = data.get("presentation")

    if "volume_ml" in data:
        product.volume_ml = data.get("volume_ml")

    if "price" in data:
        try:
            product.price = parse_decimal(data.get("price"), "price")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if "stock_quantity" in data:
        try:
            product.stock_quantity = parse_decimal(
                data.get("stock_quantity"),
                "stock_quantity"
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if "active" in data:
        product.active = bool(data.get("active"))

    if "source" in data:
        product.source = data.get("source")

    db.session.commit()

    return jsonify(product_to_dict(product))


@products_api_bp.route("/products/<int:product_id>/stock", methods=["PATCH"])
@require_api_key
def update_stock(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json() or {}

    if "stock_quantity" not in data:
        return jsonify({"error": "stock_quantity is required"}), 400

    try:
        product.stock_quantity = parse_decimal(
            data.get("stock_quantity"),
            "stock_quantity"
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    db.session.commit()

    return jsonify(product_to_dict(product))


@products_api_bp.route("/products/<int:product_id>", methods=["DELETE"])
@require_api_key
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)

    # Soft delete para no romper pedidos/históricos.
    product.active = False
    db.session.commit()

    return jsonify({
        "message": "Product deactivated",
        "product": product_to_dict(product)
    })
