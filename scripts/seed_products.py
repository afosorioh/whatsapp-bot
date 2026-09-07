from app import create_app, db
from app.models import Product

app = create_app()

products = [
    {
        "name": "Libre Pasion",
        "style": "Wheat Ale con maracuya",
        "description": "Cerveza dorada, ligera y refrescante.",
        "presentation": "Lata 330 ml",
        "volume_ml": 330,
        "price": 11500,
        "stock_quantity": 48,
        "active": True,
        "source": "seed"
    },
    {
        "name": "Libre IPA",
        "style": "IPA",
        "description": "Cerveza lupulada, aromática y amarga.",
        "presentation": "Lata 330 ml",
        "volume_ml": 330,
        "price": 13000,
        "stock_quantity": 36,
        "active": True,
        "source": "seed"
    },
    {
        "name": "Libre Avellana",
        "style": "Brown Ale con extracto de avellana",
        "description": "Cerveza oscura con notas a caramelo y nueces.",
        "presentation": "Lata 330 ml",
        "volume_ml": 330,
        "price": 11500,
        "stock_quantity": 24,
        "active": True,
        "source": "seed"
    }
]

with app.app_context():
    for item in products:
        existing = Product.query.filter_by(name=item["name"]).first()

        if existing:
            existing.style = item["style"]
            existing.description = item["description"]
            existing.presentation = item["presentation"]
            existing.volume_ml = item["volume_ml"]
            existing.price = item["price"]
            existing.stock_quantity = item["stock_quantity"]
            existing.active = item["active"]
            existing.source = item["source"]
        else:
            product = Product(**item)
            db.session.add(product)

    db.session.commit()
    print("Productos cargados correctamente.")
