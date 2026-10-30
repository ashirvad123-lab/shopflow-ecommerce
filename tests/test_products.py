from models import Product


def test_public_product_browsing(client, sample_product):
    """Test that public visitors can view catalog and product details."""
    # Homepage
    res_home = client.get('/')
    assert res_home.status_code == 200
    assert sample_product.name.encode() in res_home.data

    # Product Catalog
    res_catalog = client.get('/products')
    assert res_catalog.status_code == 200
    assert sample_product.name.encode() in res_catalog.data

    # Product Details
    res_detail = client.get(f'/products/{sample_product.id}')
    assert res_detail.status_code == 200
    assert sample_product.name.encode() in res_detail.data


def test_product_search_and_filter(client, sample_product, sample_category):
    """Test search query and category filtering."""
    # Search match
    res_search = client.get('/products?search=Wireless')
    assert res_search.status_code == 200
    assert sample_product.name.encode() in res_search.data

    # Search non-match
    res_empty = client.get('/products?search=NonExistentDevice123')
    assert res_empty.status_code == 200
    assert b'No matching products found' in res_empty.data

    # Category filter match
    res_cat = client.get(f'/products?category={sample_category.slug}')
    assert res_cat.status_code == 200
    assert sample_product.name.encode() in res_cat.data


def test_admin_create_product(client, admin_user, sample_category, app):
    """Test that administrator can create a new product."""
    # Login as admin
    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})

    response = client.post('/admin/products/new', data={
        'name': 'Brand New 4K Drone',
        'description': 'Advanced obstacle avoidance with 4K camera.',
        'price': '499.99',
        'category_id': sample_category.id,
        'image_url': 'https://example.com/drone.jpg',
        'stock': 8,
        'is_featured': 'true'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        drone = Product.query.filter_by(name='Brand New 4K Drone').first()
        assert drone is not None
        assert float(drone.price) == 499.99
        assert drone.stock == 8
        assert drone.is_featured is True


def test_non_admin_cannot_create_product(client, normal_user, sample_category):
    """Test that regular customer is rejected with 403 Forbidden when trying to access admin product creation."""
    client.post('/auth/login', data={'username_or_email': normal_user.username, 'password': 'userpass123'})

    response = client.post('/admin/products/new', data={
        'name': 'Hacked Product',
        'description': 'Should not be allowed',
        'price': '10.00',
        'category_id': sample_category.id,
        'stock': 5
    })
    assert response.status_code == 403


def test_admin_update_product_and_stock(client, admin_user, sample_product, app):
    """Test administrator editing product details and updating stock."""
    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})

    # Edit details
    res_edit = client.post(f'/admin/products/{sample_product.id}/edit', data={
        'name': 'Updated Headphones Pro',
        'description': sample_product.description,
        'price': '79.99',
        'category_id': sample_product.category_id,
        'stock': 15,
        'is_active': 'true'
    }, follow_redirects=True)
    assert res_edit.status_code == 200

    with app.app_context():
        from extensions import db
        p = db.session.get(Product, sample_product.id)
        assert p.name == 'Updated Headphones Pro'
        assert float(p.price) == 79.99

    # Quick stock update
    res_stock = client.post(f'/admin/products/{sample_product.id}/stock', data={
        'stock': 40
    }, follow_redirects=True)
    assert res_stock.status_code == 200

    with app.app_context():
        from extensions import db
        p = db.session.get(Product, sample_product.id)
        assert p.stock == 40


def test_admin_delete_product(client, admin_user, sample_product, app):
    """Test administrator deleting a product."""
    client.post('/auth/login', data={'username_or_email': admin_user.username, 'password': 'adminpass123'})

    res_del = client.post(f'/admin/products/{sample_product.id}/delete', follow_redirects=True)
    assert res_del.status_code == 200

    with app.app_context():
        from extensions import db
        p = db.session.get(Product, sample_product.id)
        assert p is None
