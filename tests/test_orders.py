from decimal import Decimal
from models import Order, OrderItem, Product
from extensions import db


def create_dummy_order(user, product, qty=2, status='Confirmed'):
    order = Order(
        order_number='ORD-TEST-12345',
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone='+1-555-1234',
        shipping_address='123 Test St',
        city='Testville',
        postal_code='12345',
        subtotal=Decimal('100.00'),
        shipping_fee=Decimal('0.00'),
        total_amount=Decimal('100.00'),
        status=status,
        payment_method='Cash on Delivery'
    )
    db.session.add(order)
    db.session.flush()

    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        product_name=product.name,
        price=product.price,
        quantity=qty,
        subtotal=Decimal('100.00')
    )
    db.session.add(item)
    db.session.commit()
    return order


def test_user_can_view_own_order(client, normal_user, sample_product, app):
    """Test user accessing their own order details."""
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p)
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    res = client.get(f'/orders/{order_id}')
    assert res.status_code == 200
    assert b'ORD-TEST-12345' in res.data


def test_user_cannot_access_other_users_order(client, normal_user, other_user, sample_product, app):
    """Test strict authorization: User 2 cannot access User 1's order (403 Forbidden)."""
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p)
        order_id = order.id

    # Log in as other_user
    client.post('/auth/login', data={'username_or_email': other_user.username, 'password': 'userpass456'})
    res = client.get(f'/orders/{order_id}')
    assert res.status_code == 403


def test_user_cancel_order_restores_inventory(client, normal_user, sample_product, app):
    """Test user cancelling order when status is Confirmed, restoring product stock."""
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        initial_stock = p.stock
        order = create_dummy_order(u, p, qty=2, status='Confirmed')
        order_id = order.id
        # Simulate stock was decremented at purchase time
        p.stock -= 2
        db.session.commit()

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    res = client.post(
        f'/orders/{order_id}/cancel',
        data={'reason': 'Changed my mind'},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b'has been cancelled and inventory restored' in res.data

    with app.app_context():
        ord_db = db.session.get(Order, order_id)
        assert ord_db.status == 'Cancelled'
        assert ord_db.cancelled_at is not None
        assert ord_db.cancellation_reason == 'Changed my mind'
        assert ord_db.status_history[-1].status == 'Cancelled'
        p_db = db.session.get(Product, sample_product.id)
        assert p_db.stock == initial_stock  # restored to initial 10


def test_repeated_cancellation_does_not_restore_inventory_twice(client, normal_user, sample_product, app):
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=2, status='Confirmed')
        p.stock -= 2
        db.session.commit()
        order_id = order.id
        expected_stock = p.stock + 2

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post(f'/orders/{order_id}/cancel')
    client.post(f'/orders/{order_id}/cancel')

    with app.app_context():
        db.session.expire_all()
        assert db.session.get(Product, sample_product.id).stock == expected_stock
        order = db.session.get(Order, order_id)
        assert [event.status for event in order.status_history].count('Cancelled') == 1


def test_shipped_order_cannot_be_cancelled_by_customer(client, normal_user, sample_product, app):
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Shipped')
        stock = p.stock
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    response = client.post(f'/orders/{order_id}/cancel', follow_redirects=True)
    assert b'Cannot change order status from Shipped to Cancelled' in response.data
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(Order, order_id).status == 'Shipped'
        assert db.session.get(Product, sample_product.id).stock == stock


def test_customer_can_download_only_their_own_pdf_invoice(client, normal_user, other_user, sample_product, app):
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1)
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    response = client.get(f'/orders/{order_id}/invoice')
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.data.startswith(b'%PDF-')
    assert 'invoice-ORD-TEST-12345.pdf' in response.headers['Content-Disposition']

    client.get('/auth/logout')
    client.post('/auth/login', data={'username_or_email': other_user.username, 'password': 'userpass456'})
    forbidden = client.get(f'/orders/{order_id}/invoice')
    assert forbidden.status_code == 403


def test_admin_cannot_skip_order_statuses(client, admin_user, normal_user, sample_product, app):
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Order Placed')
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})
    response = client.post(
        f'/admin/orders/{order_id}/status',
        data={'status': 'Shipped'},
        follow_redirects=True,
    )
    assert b'Cannot change order status from Order Placed to Shipped' in response.data
    with app.app_context():
        assert db.session.get(Order, order_id).status == 'Order Placed'


def test_customer_cannot_update_order_status(client, normal_user, sample_product, app):
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Order Placed')
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    response = client.post(f'/admin/orders/{order_id}/status', data={'status': 'Confirmed'})
    assert response.status_code == 403
    with app.app_context():
        assert db.session.get(Order, order_id).status == 'Order Placed'


def test_admin_order_list_supports_search_and_status_filter(client, admin_user, normal_user, sample_product, app):
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Confirmed')
        order_number = order.order_number

    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})
    response = client.get('/admin/orders?status=Confirmed&search=customer_one')
    assert response.status_code == 200
    assert order_number.encode() in response.data


def test_admin_can_update_order_status(client, admin_user, normal_user, sample_product, app):
    """Test administrator updating order status from Confirmed to Shipped then Delivered."""
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Confirmed')
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})

    # Update to Shipped
    res1 = client.post(
        f'/admin/orders/{order_id}/status',
        data={'status': 'Shipped', 'tracking_number': 'TRACK-123', 'courier_name': 'Parcel Co.'},
        follow_redirects=True,
    )
    assert res1.status_code == 200

    with app.app_context():
        shipped_order = db.session.get(Order, order_id)
        assert shipped_order.status == 'Shipped'
        assert shipped_order.tracking_number == 'TRACK-123'
        assert shipped_order.courier_name == 'Parcel Co.'

    # Update to Delivered
    res2 = client.post(f'/admin/orders/{order_id}/status', data={'status': 'Delivered'}, follow_redirects=True)
    assert res2.status_code == 200

    with app.app_context():
        delivered_order = db.session.get(Order, order_id)
        assert delivered_order.status == 'Delivered'
        assert [event.status for event in delivered_order.status_history] == ['Shipped', 'Delivered']


def test_order_details_displays_delivery_location(client, normal_user, sample_product, app):
    """Test user order details page displays confirmed GPS coordinates and Google Maps button."""
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Confirmed')
        order.latitude = 37.7749
        order.longitude = -122.4194
        db.session.commit()
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    res = client.get(f'/orders/{order_id}')
    assert res.status_code == 200
    assert b'GPS: 37.7749, -122.4194' in res.data
    assert b'Open Destination in Google Maps' in res.data
    assert b'orderMap' in res.data
    assert b'Real-time courier tracking is not simulated' in res.data


def test_admin_order_details_displays_delivery_location(client, admin_user, normal_user, sample_product, app):
    """Test admin order detail inspection displays coordinates and maps destination."""
    with app.app_context():
        p = db.session.get(Product, sample_product.id)
        u = db.session.get(type(normal_user), normal_user.id)
        order = create_dummy_order(u, p, qty=1, status='Confirmed')
        order.latitude = 40.7128
        order.longitude = -74.0060
        db.session.commit()
        order_id = order.id

    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})
    res = client.get(f'/admin/orders/{order_id}')
    assert res.status_code == 200
    assert b'GPS: 40.7128, -74.0060' in res.data
    assert b'Open in Google Maps' in res.data
    assert b'orderMap' in res.data
