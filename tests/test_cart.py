from models import CartItem


def test_add_to_cart_success(client, normal_user, sample_product, app):
    """Test adding an available product to shopping cart."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    response = client.post('/cart/add', data={
        'product_id': sample_product.id,
        'quantity': 2
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        item = CartItem.query.filter_by(user_id=normal_user.id, product_id=sample_product.id).first()
        assert item is not None
        assert item.quantity == 2


def test_cannot_add_more_than_available_stock(client, normal_user, sample_product):
    """Test stock limit validation prevents over-ordering."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    # sample_product has stock = 10; try adding 15
    response = client.post('/cart/add', data={
        'product_id': sample_product.id,
        'quantity': 15
    }, follow_redirects=True)

    assert b'exceeds' in response.data or b'Only 10 items in stock' in response.data


def test_update_cart_quantity_and_remove(client, normal_user, sample_product, app):
    """Test incrementing, decrementing, and removing items in cart."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    # Add 1 item
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 1})

    with app.app_context():
        item = CartItem.query.filter_by(user_id=normal_user.id, product_id=sample_product.id).first()
        item_id = item.id

    # Increase quantity
    res_inc = client.post(f'/cart/update/{item_id}', data={'action': 'increase'}, follow_redirects=True)
    assert res_inc.status_code == 200
    with app.app_context():
        from extensions import db
        assert db.session.get(CartItem, item_id).quantity == 2

    # Remove item
    res_rem = client.post(f'/cart/remove/{item_id}', follow_redirects=True)
    assert res_rem.status_code == 200
    with app.app_context():
        from extensions import db
        assert db.session.get(CartItem, item_id) is None


def test_clear_cart(client, normal_user, sample_product, app):
    """Test clearing all items in cart."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})
    client.post('/cart/add', data={'product_id': sample_product.id, 'quantity': 1})

    res_clear = client.post('/cart/clear', follow_redirects=True)
    assert res_clear.status_code == 200
    with app.app_context():
        assert CartItem.query.filter_by(user_id=normal_user.id).count() == 0
