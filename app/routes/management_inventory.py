from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.models import Product
from app.routes.management import management_required, _valid_csrf


management_inventory_bp = Blueprint(
    "management_inventory",
    __name__,
    url_prefix="/chatbot/gestion/inventario",
    template_folder="../templates",
)


def _parse_decimal(value, field_name, required=False):
    raw = (value or "").strip()

    if not raw:
        if required:
            raise ValueError(f"{field_name} is required.")
        return Decimal("0")

    try:
        number = Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc

    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")

    return number


def _parse_volume(value):
    raw = (value or "").strip()

    if not raw:
        return None

    try:
        volume = int(raw)
    except ValueError as exc:
        raise ValueError("Volume must be an integer.") from exc

    if volume <= 0:
        raise ValueError("Volume must be greater than zero.")

    return volume


def _apply_form(product):
    name = (request.form.get("name") or "").strip()

    if not name:
        raise ValueError("Name is required.")

    product.name = name
    product.style = (request.form.get("style") or "").strip() or None
    product.description = (
        (request.form.get("description") or "").strip() or None
    )
    product.presentation = (
        (request.form.get("presentation") or "").strip() or None
    )
    product.volume_ml = _parse_volume(request.form.get("volume_ml"))
    product.price = _parse_decimal(
        request.form.get("price"),
        "Price",
        required=True,
    )
    product.stock_quantity = _parse_decimal(
        request.form.get("stock_quantity"),
        "Stock",
    )
    product.active = request.form.get("active") == "on"

    if not product.source:
        product.source = "management_portal"


@management_inventory_bp.route("/")
@management_required
def list_inventory():
    active = request.args.get("active", "true").lower()

    query = Product.query.order_by(Product.name.asc(), Product.id.asc())

    if active == "true":
        query = query.filter(Product.active.is_(True))
    elif active == "false":
        query = query.filter(Product.active.is_(False))
    else:
        active = ""

    products = query.all()

    return render_template(
        "management/inventory/list.html",
        products=products,
        active=active,
    )


@management_inventory_bp.route("/new", methods=["GET", "POST"])
@management_required
def new_product():
    product = Product(
        name="",
        price=Decimal("0"),
        stock_quantity=Decimal("0"),
        active=True,
        source="management_portal",
    )

    if request.method == "POST":
        if not _valid_csrf():
            abort(400, description="Invalid CSRF token")

        try:
            _apply_form(product)
            db.session.add(product)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Product created successfully.", "success")
            return redirect(url_for("management_inventory.list_inventory"))

    return render_template(
        "management/inventory/form.html",
        product=None,
        form_data=request.form if request.method == "POST" else None,
    )


@management_inventory_bp.route(
    "/<int:product_id>/edit",
    methods=["GET", "POST"],
)
@management_required
def edit_product(product_id):
    product = db.session.get(Product, product_id)

    if not product:
        abort(404)

    if request.method == "POST":
        if not _valid_csrf():
            abort(400, description="Invalid CSRF token")

        try:
            _apply_form(product)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Product updated successfully.", "success")
            return redirect(url_for("management_inventory.list_inventory"))

    return render_template(
        "management/inventory/form.html",
        product=product,
        form_data=request.form if request.method == "POST" else None,
    )


@management_inventory_bp.route(
    "/<int:product_id>/stock",
    methods=["POST"],
)
@management_required
def update_stock(product_id):
    if not _valid_csrf():
        abort(400, description="Invalid CSRF token")

    product = db.session.get(Product, product_id)

    if not product:
        abort(404)

    try:
        product.stock_quantity = _parse_decimal(
            request.form.get("stock_quantity"),
            "Stock",
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    else:
        flash(f"Stock updated for {product.name}.", "success")

    active = request.form.get("active_filter", "true")
    return redirect(
        url_for("management_inventory.list_inventory", active=active)
    )


@management_inventory_bp.route(
    "/<int:product_id>/deactivate",
    methods=["POST"],
)
@management_required
def deactivate_product(product_id):
    if not _valid_csrf():
        abort(400, description="Invalid CSRF token")

    product = db.session.get(Product, product_id)

    if not product:
        abort(404)

    product.active = False
    db.session.commit()
    flash(f"{product.name} was deactivated.", "success")

    return redirect(url_for("management_inventory.list_inventory"))


@management_inventory_bp.route(
    "/<int:product_id>/activate",
    methods=["POST"],
)
@management_required
def activate_product(product_id):
    if not _valid_csrf():
        abort(400, description="Invalid CSRF token")

    product = db.session.get(Product, product_id)

    if not product:
        abort(404)

    product.active = True
    db.session.commit()
    flash(f"{product.name} was activated.", "success")

    return redirect(
        url_for("management_inventory.list_inventory", active="false")
    )
