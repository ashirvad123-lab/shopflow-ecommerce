import os
from decimal import Decimal
from extensions import db
from models import User, Category, Product, Order, OrderItem
from app import create_app


def run_seed():
    """Populate database with categories, rich sample products, and demo accounts."""
    db.create_all()

    # 1. Seed Categories
    categories_data = [
        {
            'name': 'Electronics',
            'slug': 'electronics',
            'description': 'High-performance gadgets, monitors, audio gear, and computing accessories.',
            'icon': 'bi-laptop'
        },
        {
            'name': 'Fashion & Apparel',
            'slug': 'fashion',
            'description': 'Comfortable everyday wear, premium jackets, sneakers, and modern accessories.',
            'icon': 'bi-bag'
        },
        {
            'name': 'Home & Living',
            'slug': 'home-living',
            'description': 'Ergonomic office furniture, kitchen essentials, and ambient lighting.',
            'icon': 'bi-house-heart'
        },
        {
            'name': 'Books & Stationery',
            'slug': 'books-stationery',
            'description': 'Computer science classics, tech guides, journals, and designer notebooks.',
            'icon': 'bi-book'
        }
    ]

    category_map = {}
    for cat_data in categories_data:
        existing = Category.query.filter_by(slug=cat_data['slug']).first()
        if not existing:
            cat = Category(**cat_data)
            db.session.add(cat)
            db.session.flush()
            category_map[cat.slug] = cat
        else:
            category_map[existing.slug] = existing

    # 2. Seed Products
    products_data = [
        # Electronics
        {
            'name': 'SoundPro Wireless Noise-Cancelling Headphones',
            'description': 'Engineered with active noise cancellation, 40mm neodymium drivers, 30-hour battery life, and ultra-plush memory foam ear cups for studio quality sound.',
            'price': Decimal('149.99'),
            'category_slug': 'electronics',
            'image_url': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80',
            'stock': 24,
            'is_featured': True
        },
        {
            'name': 'Apex Ultra 4K UHD IPS Monitor 27-inch',
            'description': 'Crisp 3840x2160 resolution with HDR400, 99% sRGB color accuracy, USB-C connectivity with 65W power delivery, and fully ergonomic tilt/swivel stand.',
            'price': Decimal('329.50'),
            'category_slug': 'electronics',
            'image_url': 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=800&auto=format&fit=crop&q=80',
            'stock': 15,
            'is_featured': True
        },
        {
            'name': 'PulseFit Smartwatch & Fitness Tracker',
            'description': 'Water-resistant OLED display, all-day heart rate & SpO2 monitoring, integrated GPS, 14-day battery life, and seamless smartphone notifications.',
            'price': Decimal('89.00'),
            'category_slug': 'electronics',
            'image_url': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800&auto=format&fit=crop&q=80',
            'stock': 30,
            'is_featured': True
        },
        {
            'name': 'AeroMechanical RGB Mechanical Keyboard',
            'description': 'Tactile hot-swappable switches, aircraft-grade aluminum top frame, sound-dampening foam, per-key RGB backlighting, and braided USB-C cable.',
            'price': Decimal('69.99'),
            'category_slug': 'electronics',
            'image_url': 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=800&auto=format&fit=crop&q=80',
            'stock': 18,
            'is_featured': False
        },

        # Fashion
        {
            'name': 'Heritage Classic Heavyweight Denim Jacket',
            'description': 'Timeless button-down styling made from durable 100% washed organic denim. Features reinforced stitching, side welt pockets, and adjustable waist tabs.',
            'price': Decimal('79.99'),
            'category_slug': 'fashion',
            'image_url': 'https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=800&auto=format&fit=crop&q=80',
            'stock': 12,
            'is_featured': True
        },
        {
            'name': 'Urban Glide Lightweight Knit Sneakers',
            'description': 'Breathable engineered mesh upper paired with shock-absorbing cloud foam midsole. Designed for all-day campus walking and daily workouts.',
            'price': Decimal('94.50'),
            'category_slug': 'fashion',
            'image_url': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800&auto=format&fit=crop&q=80',
            'stock': 20,
            'is_featured': True
        },
        {
            'name': 'Skyline Polarized Classic Aviator Sunglasses',
            'description': 'Lightweight stainless steel frame with scratch-resistant UV400 polarized lenses that eliminate glare and provide optimal clarity.',
            'price': Decimal('39.99'),
            'category_slug': 'fashion',
            'image_url': 'https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=800&auto=format&fit=crop&q=80',
            'stock': 25,
            'is_featured': False
        },

        # Home & Living
        {
            'name': 'ErgoMesh High-Back Ergonomic Office Chair',
            'description': 'Breathable Korean mesh backrest, 3D adjustable armrests, pneumatic seat height adjustment, and dynamic lumbar support to prevent fatigue during long coding sessions.',
            'price': Decimal('199.00'),
            'category_slug': 'home-living',
            'image_url': 'https://images.unsplash.com/photo-1598300056393-4aac492f4344?w=800&auto=format&fit=crop&q=80',
            'stock': 8,
            'is_featured': True
        },
        {
            'name': 'AromaPress Italian Style Stainless Espresso Maker',
            'description': 'Stovetop moka pot forged from food-grade stainless steel with cool-touch ergonomic handle. Produces rich, velvety espresso in under 5 minutes.',
            'price': Decimal('54.95'),
            'category_slug': 'home-living',
            'image_url': 'https://images.unsplash.com/photo-1517668808822-9ebb02f2a0e6?w=800&auto=format&fit=crop&q=80',
            'stock': 16,
            'is_featured': False
        },
        {
            'name': 'Lumina Dimmable LED Desk Lamp with Wireless Charger',
            'description': 'Touch-controlled color temperatures (warm, natural, cool) with memory setting and an integrated 10W Qi fast wireless charging base.',
            'price': Decimal('34.99'),
            'category_slug': 'home-living',
            'image_url': 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=800&auto=format&fit=crop&q=80',
            'stock': 4,  # Intentional low stock to test alerts!
            'is_featured': False
        },

        # Books & Stationery
        {
            'name': 'Clean Code: A Handbook of Agile Software Craftsmanship',
            'description': 'Essential reading for every software engineer. Learn the principles, patterns, and practices of writing maintainable, professional, clean code.',
            'price': Decimal('42.99'),
            'category_slug': 'books-stationery',
            'image_url': 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=800&auto=format&fit=crop&q=80',
            'stock': 22,
            'is_featured': True
        },
        {
            'name': 'Architect Hardcover Leather Grid Notebook',
            'description': '240 numbered pages of 120gsm ink-proof fountain pen paper with ribbon bookmark, expandable inner pocket, and dot-grid ruling.',
            'price': Decimal('24.50'),
            'category_slug': 'books-stationery',
            'image_url': 'https://images.unsplash.com/photo-1531346878377-a5be20888e57?w=800&auto=format&fit=crop&q=80',
            'stock': 35,
            'is_featured': False
        }
    ]

    for p_data in products_data:
        existing_p = Product.query.filter_by(name=p_data['name']).first()
        cat = category_map[p_data['category_slug']]
        if not existing_p:
            p = Product(
                name=p_data['name'],
                description=p_data['description'],
                price=p_data['price'],
                category_id=cat.id,
                image_url=p_data['image_url'],
                stock=p_data['stock'],
                is_featured=p_data['is_featured'],
                is_active=True
            )
            db.session.add(p)
        else:
            # Update fields if already exists
            existing_p.category_id = cat.id
            existing_p.image_url = p_data['image_url']
            existing_p.price = p_data['price']

    # 3. Seed Admin and Customer Users
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(
            username=os.getenv('ADMIN_USERNAME', 'admin'),
            email=os.getenv('ADMIN_EMAIL', 'admin@shop.com'),
            full_name='System Administrator',
            role='admin',
            phone='+1-800-555-0100',
            address='Admin Operations Center, Suite 100',
            city='Tech City',
            postal_code='10001'
        )
        admin_user.set_password(os.getenv('ADMIN_PASSWORD', 'admin123'))
        db.session.add(admin_user)

    customer_user = User.query.filter_by(username='john_doe').first()
    if not customer_user:
        customer_user = User(
            username='john_doe',
            email='user@shop.com',
            full_name='John Doe',
            role='user',
            phone='+1-555-019-2834',
            address='452 Campus Avenue, Apt 3B',
            city='Metro City',
            postal_code='94016'
        )
        customer_user.set_password('user123')
        db.session.add(customer_user)
        db.session.flush()

    db.session.commit()
    print("Database seeding completed successfully.")


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        run_seed()
