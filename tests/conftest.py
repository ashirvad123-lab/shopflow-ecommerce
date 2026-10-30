import pytest
from decimal import Decimal
from app import create_app
from extensions import db
from models import User, Category, Product


@pytest.fixture
def app():
    """Create and configure a testing Flask app instance."""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Test client for simulating HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """CLI test runner."""
    return app.test_cli_runner()


@pytest.fixture
def admin_user(app):
    """Create and return an administrator user."""
    admin = User(
        username='admin_test',
        email='admin@test.com',
        full_name='Admin Tester',
        role='admin'
    )
    admin.set_password('adminpass123')
    db.session.add(admin)
    db.session.commit()
    return admin


@pytest.fixture
def normal_user(app):
    """Create and return a regular customer user."""
    user = User(
        username='customer_one',
        email='customer1@test.com',
        full_name='Customer One',
        role='user',
        address='123 Test Street',
        city='Testville',
        postal_code='12345',
        phone='+1-555-1111'
    )
    user.set_password('userpass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def other_user(app):
    """Create and return a secondary customer user to verify isolation."""
    user = User(
        username='customer_two',
        email='customer2@test.com',
        full_name='Customer Two',
        role='user',
        address='456 Another Road',
        city='SecondCity',
        postal_code='67890',
        phone='+1-555-2222'
    )
    user.set_password('userpass456')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_category(app):
    """Create and return a sample category."""
    category = Category(
        name='Electronics',
        slug='electronics',
        description='Electronic gadgets and hardware',
        icon='bi-laptop'
    )
    db.session.add(category)
    db.session.commit()
    return category


@pytest.fixture
def sample_product(app, sample_category):
    """Create and return a sample product with known stock and price."""
    product = Product(
        name='Test Wireless Headphones',
        description='High fidelity sound with long battery life.',
        price=Decimal('50.00'),
        category_id=sample_category.id,
        image_url='https://example.com/test.jpg',
        stock=10,
        is_featured=True,
        is_active=True
    )
    db.session.add(product)
    db.session.commit()
    return product
