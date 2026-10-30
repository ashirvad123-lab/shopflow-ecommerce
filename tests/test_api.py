def test_api_products_list_and_detail(client, sample_product):
    """Test REST API product listing and individual product retrieval."""
    # List products
    res = client.get('/api/products')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['count'] >= 1
    assert any(p['id'] == sample_product.id for p in data['products'])

    # Get single product
    res_single = client.get(f'/api/products/{sample_product.id}')
    assert res_single.status_code == 200
    single_data = res_single.get_json()
    assert single_data['success'] is True
    assert single_data['product']['name'] == sample_product.name


def test_api_create_product_admin_only(client, admin_user, normal_user, sample_category):
    """Test that POST /api/products is restricted to Admins only."""
    # 1. Unauthenticated or normal user gets 403
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    res_forbidden = client.post('/api/products', json={
        'name': 'Hacked API Product',
        'description': 'Test',
        'price': 20.00,
        'category_id': sample_category.id
    })
    assert res_forbidden.status_code == 403

    # Log out normal_user
    client.get('/auth/logout')

    # 2. Admin gets 201 Created
    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})
    res_admin = client.post('/api/products', json={
        'name': 'API Camera Ultra',
        'description': '4K streaming webcam with microphone',
        'price': 89.99,
        'category_id': sample_category.id,
        'stock': 12
    })
    assert res_admin.status_code == 201
    created_data = res_admin.get_json()
    assert created_data['success'] is True
    assert created_data['product']['name'] == 'API Camera Ultra'


def test_api_cart_flow(client, normal_user, sample_product):
    """Test Cart REST API: add item, get cart, update item."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    # Add to cart
    res_add = client.post('/api/cart/add', json={
        'product_id': sample_product.id,
        'quantity': 2
    })
    assert res_add.status_code == 200
    assert res_add.get_json()['success'] is True

    # Get cart
    res_get = client.get('/api/cart')
    assert res_get.status_code == 200
    cart_data = res_get.get_json()
    assert cart_data['success'] is True
    assert len(cart_data['items']) == 1
    assert cart_data['total_items'] == 2


def test_api_checkout_flow(client, normal_user, sample_product, app):
    """Test Order placement via POST /api/checkout."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    # Add item to cart first
    client.post('/api/cart/add', json={'product_id': sample_product.id, 'quantity': 1})

    # Call checkout API
    res_checkout = client.post('/api/checkout', json={
        'full_name': 'Customer One',
        'email': 'customer1@test.com',
        'phone': '+1-555-1111',
        'shipping_address': '123 Test Street',
        'city': 'Testville',
        'postal_code': '12345',
        'payment_method': 'Cash on Delivery'
    })

    assert res_checkout.status_code == 201
    data = res_checkout.get_json()
    assert data['success'] is True
    assert 'order' in data
    assert data['order']['customer_name'] == 'Customer One'
    assert data['order']['status'] == 'Order Placed'
    assert data['order']['payment_status'] == 'Pending'

    # Get user orders via API
    res_orders = client.get('/api/orders')
    assert res_orders.status_code == 200
    orders_data = res_orders.get_json()
    assert orders_data['success'] is True
    assert orders_data['count'] == 1


def test_api_admin_order_status_update(client, admin_user, normal_user, sample_product):
    """Test Admin updating order status via PUT /api/admin/orders/<id>/status."""
    # Place order as normal user
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/api/cart/add', json={'product_id': sample_product.id, 'quantity': 1})
    res_checkout = client.post('/api/checkout', json={
        'full_name': 'Customer One',
        'email': 'customer1@test.com',
        'phone': '+1-555-1111',
        'shipping_address': '123 Test Street',
        'city': 'Testville',
        'postal_code': '12345'
    })
    order_id = res_checkout.get_json()['order']['id']

    # Log out normal_user
    client.get('/auth/logout')

    # Admin updates status
    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})
    res_confirm = client.put(f'/api/admin/orders/{order_id}/status', json={'status': 'Confirmed'})
    assert res_confirm.status_code == 200
    res_update = client.put(f'/api/admin/orders/{order_id}/status', json={'status': 'Shipped'})
    assert res_update.status_code == 200
    assert res_update.get_json()['order']['status'] == 'Shipped'


def test_api_checkout_with_coordinates(client, normal_user, sample_product):
    """Test API checkout correctly accepts and stores latitude & longitude."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/api/cart/add', json={'product_id': sample_product.id, 'quantity': 1})

    res = client.post('/api/checkout', json={
        'full_name': 'Customer Geo API',
        'email': 'geoapi@test.com',
        'phone': '+1-555-4321',
        'shipping_address': '456 Mission St',
        'city': 'San Francisco',
        'postal_code': '94105',
        'latitude': 37.7891,
        'longitude': -122.4014
    })

    assert res.status_code == 201
    data = res.get_json()
    assert data['success'] is True
    order = data['order']
    assert order['latitude'] == 37.7891
    assert order['longitude'] == -122.4014
    assert order['has_coordinates'] is True
    assert '37.7891' in order['google_maps_url']


def test_api_checkout_invalid_coordinates_rejected(client, normal_user, sample_product):
    """Test API checkout rejects invalid coordinates out of range."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/api/cart/add', json={'product_id': sample_product.id, 'quantity': 1})

    res = client.post('/api/checkout', json={
        'full_name': 'Customer Bad Geo API',
        'email': 'badgeoapi@test.com',
        'phone': '+1-555-4321',
        'shipping_address': '456 Mission St',
        'city': 'San Francisco',
        'postal_code': '94105',
        'latitude': 195.0,  # Invalid latitude (> 90)
        'longitude': -122.4014
    })

    assert res.status_code == 400
    data = res.get_json()
    assert data['success'] is False
    assert 'Latitude must be between -90.0 and 90.0 degrees' in data['error']
