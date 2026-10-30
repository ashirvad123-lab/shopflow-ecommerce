from models import Product, Order, OrderItem, CartItem
from extensions import db


def test_checkout_empty_cart_redirects(client, normal_user):
    """Test checkout cannot proceed with an empty cart."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    response = client.get('/checkout/', follow_redirects=True)
    assert b'Your shopping cart is empty' in response.data


def test_successful_checkout_and_inventory_decrement(client, normal_user, sample_product, app):
    """Test full checkout flow: Order creation, OrderItem creation, stock decrement, cart clearing."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    initial_stock = sample_product.stock
    purchase_qty = 3

    # Add to cart
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': purchase_qty})

    # Place order
    response = client.post('/checkout/place-order', data={
        'full_name': 'Customer One',
        'email': 'customer1@test.com',
        'phone': '+1-555-1111',
        'shipping_address': '123 Test Street',
        'city': 'Testville',
        'postal_code': '12345',
        'payment_method': 'Cash on Delivery',
        'notes': 'Please ring doorbell'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'placed successfully' in response.data

    with app.app_context():
        # 1. Verify Order created
        order = Order.query.filter_by(user_id=normal_user.id).first()
        assert order is not None
        assert order.status == 'Order Placed'
        assert order.payment_status == 'Pending'
        assert len(order.status_history) == 1
        assert order.status_history[0].status == 'Order Placed'
        assert order.full_name == 'Customer One'
        assert float(order.subtotal) == 150.00
        assert float(order.total_amount) == 150.00

        # 2. Verify OrderItems
        assert len(order.items) == 1
        assert order.items[0].product_name == sample_product.name
        assert order.items[0].quantity == purchase_qty
        assert float(order.items[0].subtotal) == 150.00

        # 3. Verify Product inventory decremented (10 - 3 = 7)
        product = db.session.get(Product, sample_product.id)
        assert product.stock == initial_stock - purchase_qty

        # 4. Verify Cart was cleared
        assert CartItem.query.filter_by(user_id=normal_user.id).count() == 0


def test_checkout_order_is_persisted_and_visible_in_my_orders(
    client, normal_user, other_user, sample_product, app
):
    client.post('/auth/login', data={
        'username_or_email': normal_user.username,
        'password': 'userpass123',
    })
    client.post('/cart/add', data={
        'product_id': sample_product.id,
        'quantity': 2,
    })

    checkout = client.post('/checkout/place-order', data={
        'full_name': 'Customer One',
        'email': normal_user.email,
        'phone': '+1-555-1111',
        'shipping_address': '123 Test Street',
        'city': 'Testville',
        'postal_code': '12345',
        'payment_method': 'Cash on Delivery',
    })

    assert checkout.status_code == 302
    assert '/checkout/confirmation/' in checkout.headers['Location']

    with app.app_context():
        order = Order.query.filter_by(user_id=normal_user.id).one()
        order_id = order.id
        order_number = order.order_number
        order_date = order.created_at.strftime('%Y-%m-%d')
        assert order.status == 'Order Placed'
        assert order.payment_status == 'Pending'
        assert float(order.subtotal) == 100.00
        assert float(order.total_amount) == 100.00
        assert len(order.items) == 1
        assert order.items[0].product_name == sample_product.name
        assert order.items[0].quantity == 2
        assert float(order.items[0].price) == 50.00

    confirmation = client.get(checkout.headers['Location'])
    assert confirmation.status_code == 200
    assert order_number.encode() in confirmation.data

    history = client.get('/orders/')
    assert history.status_code == 200
    assert order_number.encode() in history.data
    assert b'Order Placed' in history.data
    assert b'$100.00' in history.data

    refreshed_history = client.get('/orders/')
    assert refreshed_history.status_code == 200
    assert order_number.encode() in refreshed_history.data
    filtered_history = client.get(
        f'/orders/?status=Order+Placed&start_date={order_date}&end_date={order_date}'
    )
    assert filtered_history.status_code == 200
    assert order_number.encode() in filtered_history.data
    no_matching_filter = client.get('/orders/?status=Cancelled')
    assert no_matching_filter.status_code == 200
    assert b'No orders match these filters' in no_matching_filter.data
    assert b'No orders placed yet' not in no_matching_filter.data

    client.get('/auth/logout')
    client.post('/auth/login', data={
        'username_or_email': other_user.username,
        'password': 'userpass456',
    })
    other_history = client.get('/orders/')
    assert other_history.status_code == 200
    assert order_number.encode() not in other_history.data
    assert client.get(f'/orders/{order_id}').status_code == 403


def test_demo_card_checkout_is_not_marked_as_paid(client, normal_user, sample_product, app):
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 1})
    response = client.post('/checkout/place-order', data={
        'full_name': 'Customer One',
        'email': 'customer1@test.com',
        'phone': '+1-555-1111',
        'shipping_address': '123 Test Street',
        'city': 'Testville',
        'postal_code': '12345',
        'payment_method': 'Demo Card / Net Banking',
    })
    assert response.status_code == 302
    with app.app_context():
        order = Order.query.filter_by(user_id=normal_user.id).one()
        assert order.payment_method == 'Demo Card / Net Banking'
        assert order.payment_status == 'Pending'


def test_checkout_fails_if_stock_became_insufficient(client, normal_user, sample_product, app):
    """Test transaction aborts and informs user if product stock drops before checkout."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    # User adds 5 to cart
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 5})

    # Stock is externally reduced to 2 (e.g., by another simultaneous buyer)
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        p.stock = 2
        db.session.commit()

    # Attempt to place order
    response = client.post('/checkout/place-order', data={
        'full_name': 'Customer One',
        'email': 'customer1@test.com',
        'phone': '+1-555-1111',
        'shipping_address': '123 Test Street',
        'city': 'Testville',
        'postal_code': '12345',
        'payment_method': 'Cash on Delivery'
    }, follow_redirects=True)

    assert b'Insufficient stock' in response.data


def test_checkout_with_valid_coordinates(client, normal_user, sample_product, app):
    """Test checkout successfully stores latitude and longitude delivery pin."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 1})

    response = client.post('/checkout/place-order', data={
        'full_name': 'Customer Geo',
        'email': 'geo@test.com',
        'phone': '+1-555-8888',
        'shipping_address': '500 Market St',
        'city': 'San Francisco',
        'postal_code': '94105',
        'payment_method': 'Cash on Delivery',
        'latitude': '37.7749',
        'longitude': '-122.4194'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'placed successfully' in response.data

    with app.app_context():
        order = Order.query.filter_by(user_id=normal_user.id).order_by(Order.id.desc()).first()
        assert order is not None
        assert order.latitude == 37.7749
        assert order.longitude == -122.4194
        assert order.has_coordinates is True
        assert '37.7749%2C-122.4194' in order.google_maps_url or '37.7749,-122.4194' in order.google_maps_url


def test_checkout_with_invalid_coordinates_rejected(client, normal_user, sample_product, app):
    """Test checkout rejects out-of-range or malformed coordinates."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 1})

    # Latitude > 90 is invalid
    response = client.post('/checkout/place-order', data={
        'full_name': 'Customer Bad Geo',
        'email': 'badgeo@test.com',
        'phone': '+1-555-9999',
        'shipping_address': '999 North Pole St',
        'city': 'San Francisco',
        'postal_code': '94105',
        'payment_method': 'Cash on Delivery',
        'latitude': '105.5',
        'longitude': '-122.4194'
    }, follow_redirects=True)

    assert b'Latitude must be between -90.0 and 90.0 degrees' in response.data

    with app.app_context():
        order = Order.query.filter_by(full_name='Customer Bad Geo').first()
        assert order is None


def test_checkout_without_coordinates_fallback(client, normal_user, sample_product, app):
    """Test checkout works seamlessly when coordinates are omitted (fallback address mode)."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 1})

    response = client.post('/checkout/place-order', data={
        'full_name': 'Customer Fallback',
        'email': 'fallback@test.com',
        'phone': '+1-555-7777',
        'shipping_address': '777 Fallback Way',
        'city': 'San Francisco',
        'postal_code': '94105',
        'payment_method': 'Cash on Delivery',
        'latitude': '',
        'longitude': ''
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'placed successfully' in response.data

    with app.app_context():
        order = Order.query.filter_by(full_name='Customer Fallback').first()
        assert order is not None
        assert order.latitude is None
        assert order.longitude is None
        assert order.has_coordinates is False
        assert '777+Fallback+Way' in order.google_maps_url or '777%20Fallback%20Way' in order.google_maps_url
