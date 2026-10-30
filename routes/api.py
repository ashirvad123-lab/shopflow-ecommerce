import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request, abort, current_app
from flask_login import current_user
from sqlalchemy import update
from extensions import db, csrf
from models import Product, Category, CartItem, Order, OrderItem, User
from routes.cart import calculate_cart_totals
from routes.checkout import parse_and_validate_coordinates
from services.order_tracking import record_initial_order_status, transition_order

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Helper error response
def error_response(message: str, status_code: int = 400):
    return jsonify({'success': False, 'error': message}), status_code


# -------------------------------------------------------------
# Products REST API
# -------------------------------------------------------------

@api_bp.route('/products', methods=['GET'])
def get_products():
    """List products with optional search, category, and sorting."""
    search = request.args.get('search', '').strip()
    category_slug = request.args.get('category', '').strip()
    sort = request.args.get('sort', 'newest')

    query = Product.query.filter_by(is_active=True)

    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first()
        if cat:
            query = query.filter(Product.category_id == cat.id)

    if search:
        query = query.filter(
            (Product.name.ilike(f"%{search}%")) | (Product.description.ilike(f"%{search}%"))
        )

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.all()
    return jsonify({
        'success': True,
        'count': len(products),
        'products': [p.to_dict() for p in products]
    }), 200


@api_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Retrieve detailed information for a single product."""
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        return error_response('Product not found', 404)
    return jsonify({'success': True, 'product': product.to_dict()}), 200


@api_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product (Admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return error_response('Admin authorization required', 403)

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    price = data.get('price')
    category_id = data.get('category_id')
    image_url = data.get('image_url', '').strip()
    stock = data.get('stock', 0)
    is_featured = bool(data.get('is_featured', False))

    if not name or not description or price is None or not category_id:
        return error_response('Name, description, price, and category_id are required fields', 400)

    try:
        price_val = Decimal(str(price))
        if price_val < 0:
            return error_response('Price must be greater than or equal to 0', 400)
    except Exception:
        return error_response('Invalid price format', 400)

    if not db.session.get(Category, category_id):
        return error_response(f'Category with id {category_id} does not exist', 404)

    product = Product(
        name=name,
        description=description,
        price=price_val,
        category_id=category_id,
        image_url=image_url or 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80',
        stock=max(0, int(stock)),
        is_featured=is_featured,
        is_active=True
    )
    db.session.add(product)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Product created successfully', 'product': product.to_dict()}), 201


@api_bp.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Update an existing product (Admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return error_response('Admin authorization required', 403)

    product = db.session.get(Product, product_id)
    if not product:
        return error_response('Product not found', 404)

    data = request.get_json() or {}
    if 'name' in data:
        product.name = data['name'].strip()
    if 'description' in data:
        product.description = data['description'].strip()
    if 'price' in data:
        try:
            val = Decimal(str(data['price']))
            if val < 0:
                return error_response('Price cannot be negative', 400)
            product.price = val
        except Exception:
            return error_response('Invalid price value', 400)
    if 'category_id' in data:
        if not db.session.get(Category, data['category_id']):
            return error_response('Category not found', 404)
        product.category_id = data['category_id']
    if 'image_url' in data:
        product.image_url = data['image_url'].strip()
    if 'stock' in data:
        product.stock = max(0, int(data['stock']))
    if 'is_featured' in data:
        product.is_featured = bool(data['is_featured'])
    if 'is_active' in data:
        product.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'success': True, 'message': 'Product updated successfully', 'product': product.to_dict()}), 200


@api_bp.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete or deactivate a product (Admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return error_response('Admin authorization required', 403)

    product = db.session.get(Product, product_id)
    if not product:
        return error_response('Product not found', 404)

    # Check for existing orders
    has_orders = OrderItem.query.filter_by(product_id=product.id).first() is not None
    if has_orders:
        product.is_active = False
        product.stock = 0
        db.session.commit()
        return jsonify({'success': True, 'message': 'Product deactivated because order history exists'}), 200

    db.session.delete(product)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Product deleted permanently'}), 200


# -------------------------------------------------------------
# Cart REST API
# -------------------------------------------------------------

@api_bp.route('/cart', methods=['GET'])
def get_cart():
    """Retrieve current user's cart."""
    if not current_user.is_authenticated:
        return error_response('Authentication required to view cart', 401)

    totals = calculate_cart_totals(current_user.id)
    return jsonify({
        'success': True,
        'items': [item.to_dict() for item in totals['items']],
        'total_items': totals['total_items'],
        'subtotal': float(totals['subtotal']),
        'shipping_fee': float(totals['shipping_fee']),
        'grand_total': float(totals['grand_total']),
        'free_shipping_eligible': totals['free_shipping_eligible']
    }), 200


@api_bp.route('/cart/add', methods=['POST'])
def add_to_cart_api():
    """Add a product to cart."""
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    data = request.get_json() or {}
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))

    if not product_id or quantity <= 0:
        return error_response('Valid product_id and positive quantity are required', 400)

    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        return error_response('Product not found or unavailable', 404)

    if product.stock <= 0:
        return error_response(f'"{product.name}" is currently out of stock', 400)

    existing_item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    new_quantity = quantity if not existing_item else existing_item.quantity + quantity

    if new_quantity > product.stock:
        return error_response(f'Requested quantity exceeds stock. Available: {product.stock}', 400)

    if existing_item:
        existing_item.quantity = new_quantity
    else:
        new_item = CartItem(user_id=current_user.id, product_id=product.id, quantity=quantity)
        db.session.add(new_item)

    db.session.commit()
    totals = calculate_cart_totals(current_user.id)
    return jsonify({
        'success': True,
        'message': f'"{product.name}" added to cart',
        'cart_count': totals['total_items'],
        'grand_total': float(totals['grand_total'])
    }), 200


@api_bp.route('/cart/update', methods=['PUT'])
def update_cart_api():
    """Update item quantity in cart."""
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    data = request.get_json() or {}
    item_id = data.get('item_id')
    quantity = data.get('quantity')

    if not item_id or quantity is None:
        return error_response('item_id and quantity are required', 400)

    cart_item = db.session.get(CartItem, item_id)
    if not cart_item or cart_item.user_id != current_user.id:
        return error_response('Cart item not found', 404)

    try:
        qty = int(quantity)
    except (ValueError, TypeError):
        return error_response('Quantity must be an integer', 400)

    if qty <= 0:
        db.session.delete(cart_item)
        db.session.commit()
        totals = calculate_cart_totals(current_user.id)
        return jsonify({
            'success': True,
            'message': 'Item removed from cart',
            'item_removed': True,
            'cart_count': totals['total_items'],
            'grand_total': float(totals['grand_total'])
        }), 200

    if qty > cart_item.product.stock:
        return error_response(f'Requested quantity exceeds available stock ({cart_item.product.stock})', 400)

    cart_item.quantity = qty
    db.session.commit()
    totals = calculate_cart_totals(current_user.id)
    return jsonify({
        'success': True,
        'message': 'Cart quantity updated',
        'item': cart_item.to_dict(),
        'cart_count': totals['total_items'],
        'grand_total': float(totals['grand_total'])
    }), 200


@api_bp.route('/cart/remove/<int:item_id>', methods=['DELETE'])
def remove_from_cart_api(item_id):
    """Remove item from cart."""
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    cart_item = db.session.get(CartItem, item_id)
    if not cart_item or cart_item.user_id != current_user.id:
        return error_response('Cart item not found', 404)

    db.session.delete(cart_item)
    db.session.commit()
    totals = calculate_cart_totals(current_user.id)
    return jsonify({
        'success': True,
        'message': 'Item removed from cart',
        'cart_count': totals['total_items'],
        'grand_total': float(totals['grand_total'])
    }), 200


# -------------------------------------------------------------
# Orders REST API
# -------------------------------------------------------------

@api_bp.route('/checkout', methods=['POST'])
def api_checkout():
    """Create an order from cart items."""
    if not current_user.is_authenticated:
        return error_response('Authentication required to checkout', 401)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('Checkout data must be a JSON object', 400)
    fields = {
        'full_name': 100,
        'email': 120,
        'phone': 20,
        'shipping_address': 1000,
        'city': 64,
        'postal_code': 20,
        'notes': 2000,
    }
    if any(not isinstance(data.get(name, ''), str) for name in fields):
        return error_response('Checkout fields must contain text values', 400)
    if any(len(data.get(name, '')) > limit for name, limit in fields.items()):
        return error_response('One or more checkout fields exceed the maximum length', 400)
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    shipping_address = data.get('shipping_address', '').strip()
    city = data.get('city', '').strip()
    postal_code = data.get('postal_code', '').strip()
    payment_method = data.get('payment_method', 'Cash on Delivery')
    notes = data.get('notes', '').strip()
    if not isinstance(payment_method, str) or payment_method not in {'Cash on Delivery', 'Demo Card / Net Banking'}:
        return error_response('Choose a supported payment method', 400)

    raw_lat = data.get('latitude')
    raw_lng = data.get('longitude')
    lat, lng, coord_err = parse_and_validate_coordinates(raw_lat, raw_lng)
    if coord_err:
        return error_response(coord_err, 400)

    if not full_name or not email or not phone or not shipping_address or not city or not postal_code:
        return error_response('All shipping fields are required (full_name, email, phone, shipping_address, city, postal_code)', 400)

    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        return error_response('Cannot checkout with an empty cart', 400)

    db.session.expire_all()
    subtotal = Decimal('0.00')
    for item in cart_items:
        product = db.session.get(Product, item.product_id, execution_options={"populate_existing": True})
        if not product or not product.is_active:
            return error_response(f'Product {item.product_id} is no longer active', 400)
        if item.quantity > product.stock:
            return error_response(f'Insufficient stock for "{product.name}". Available: {product.stock}', 400)
        subtotal += Decimal(str(product.price)) * item.quantity

    shipping_fee = Decimal('0.00') if subtotal >= Decimal('50.00') else Decimal('5.00')
    grand_total = subtotal + shipping_fee

    try:
        order_number = f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        order = Order(
            order_number=order_number,
            user_id=current_user.id,
            full_name=full_name,
            email=email,
            phone=phone,
            shipping_address=shipping_address,
            city=city,
            postal_code=postal_code,
            latitude=lat,
            longitude=lng,
            payment_method=payment_method,
            payment_status='Pending',
            subtotal=subtotal,
            discount_amount=Decimal('0.00'),
            shipping_fee=shipping_fee,
            total_amount=grand_total,
            status='Order Placed',
            estimated_delivery_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5),
            notes=notes
        )
        db.session.add(order)
        db.session.flush()
        record_initial_order_status(order, current_user)

        for item in cart_items:
            product = db.session.get(Product, item.product_id)
            stock_update = db.session.execute(
                update(Product)
                .where(Product.id == product.id, Product.stock >= item.quantity)
                .values(stock=Product.stock - item.quantity)
            )
            if stock_update.rowcount != 1:
                raise ValueError(f'Insufficient stock for "{product.name}". Please try again.')
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=item.quantity,
                subtotal=Decimal(str(product.price)) * item.quantity
            )
            db.session.add(order_item)
            db.session.delete(item)

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Order placed successfully',
            'order': order.to_dict()
        }), 201

    except ValueError as e:
        db.session.rollback()
        return error_response(str(e), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API checkout failed for user %s', current_user.id)
        return error_response('Order processing failed. Please try again.', 500)


@api_bp.route('/orders', methods=['GET'])
def get_user_orders():
    """Retrieve authenticated user's order history."""
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return jsonify({
        'success': True,
        'count': len(orders),
        'orders': [o.to_dict() for o in orders]
    }), 200


@api_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order_detail(order_id):
    """Retrieve details for a single order (user must own the order or be admin)."""
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    order = db.session.get(Order, order_id)
    if not order:
        return error_response('Order not found', 404)

    if order.user_id != current_user.id and not current_user.is_admin:
        return error_response('Access forbidden: You can only view your own orders', 403)

    return jsonify({'success': True, 'order': order.to_dict()}), 200


# -------------------------------------------------------------
# Admin Orders REST API
# -------------------------------------------------------------

@api_bp.route('/admin/orders', methods=['GET'])
def admin_get_orders():
    """List all customer orders with status filter (Admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return error_response('Admin authorization required', 403)

    status = request.args.get('status', '').strip()
    query = Order.query
    if status:
        query = query.filter_by(status=status)

    orders = query.order_by(Order.created_at.desc()).all()
    return jsonify({
        'success': True,
        'count': len(orders),
        'orders': [o.to_dict() for o in orders]
    }), 200


@api_bp.route('/admin/orders/<int:order_id>/status', methods=['PUT'])
def admin_update_order_status(order_id):
    """Update order status (Admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return error_response('Admin authorization required', 403)

    order = db.session.get(Order, order_id)
    if not order:
        return error_response('Order not found', 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('Request data must be a JSON object', 400)
    raw_status = data.get('status')
    if not isinstance(raw_status, str):
        return error_response('A string order status is required', 400)
    new_status = raw_status.strip()

    if new_status not in Order.STATUS_CHOICES:
        return error_response(f'Invalid status "{new_status}". Allowed: {", ".join(Order.STATUS_CHOICES)}', 400)

    tracking_number = data.get('tracking_number', '')
    courier_name = data.get('courier_name', '')
    note = data.get('reason', '')
    if (
        not isinstance(tracking_number, str) or not isinstance(courier_name, str)
        or not isinstance(note, str) or len(tracking_number) > 100
        or len(courier_name) > 100 or len(note) > 1000
    ):
        return error_response('Tracking details and status note must be text within their length limits', 400)
    note = note.strip()
    try:
        transition_order(
            order,
            new_status,
            actor=current_user,
            note=note or None,
            tracking_number=tracking_number,
            courier_name=courier_name,
        )
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return error_response(str(error), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update order status through API for order %s', order.order_number)
        return error_response('Order status update failed', 500)

    return jsonify({
        'success': True,
        'message': f'Order status updated to {new_status}',
        'order': order.to_dict()
    }), 200
