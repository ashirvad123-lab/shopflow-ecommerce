import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import update
from extensions import db
from models import Product, CartItem, Order, OrderItem
from routes.cart import calculate_cart_totals
from services.order_tracking import record_initial_order_status

checkout_bp = Blueprint('checkout', __name__, url_prefix='/checkout')


def is_order_recent(order, max_seconds=30) -> bool:
    """Check if an order was placed very recently (prevents double-order issues)."""
    if not order or not order.created_at:
        return False
    try:
        now = datetime.now(timezone.utc)
        order_time = order.created_at
        if order_time.tzinfo is None:
            order_time = order_time.replace(tzinfo=timezone.utc)
        return abs((now - order_time).total_seconds()) < max_seconds
    except Exception:
        return False


def generate_order_number() -> str:
    """Generate a clean, professional, unique order number."""
    now_str = datetime.now(timezone.utc).strftime('%Y%m%d')
    random_suffix = uuid.uuid4().hex[:6].upper()
    return f"ORD-{now_str}-{random_suffix}"


def parse_and_validate_coordinates(lat_val, lng_val):
    """
    Validates latitude and longitude inputs.
    Returns (float_lat, float_lng, error_message).
    If both are absent or empty, returns (None, None, None).
    """
    if lat_val is None and lng_val is None:
        return None, None, None

    lat_str = str(lat_val).strip() if lat_val is not None else ''
    lng_str = str(lng_val).strip() if lng_val is not None else ''

    if not lat_str and not lng_str:
        return None, None, None

    if (lat_str and not lng_str) or (lng_str and not lat_str):
        return None, None, 'Both latitude and longitude must be provided together.'

    try:
        lat = float(lat_str)
        lng = float(lng_str)
    except (ValueError, TypeError):
        return None, None, 'Invalid coordinate format. Latitude and longitude must be valid floating-point numbers.'

    if not (-90.0 <= lat <= 90.0):
        return None, None, f'Latitude must be between -90.0 and 90.0 degrees (received {lat}).'

    if not (-180.0 <= lng <= 180.0):
        return None, None, f'Longitude must be between -180.0 and 180.0 degrees (received {lng}).'

    return lat, lng, None


@checkout_bp.route('', methods=['GET', 'POST'])
@checkout_bp.route('/', methods=['GET', 'POST'])
@login_required
def checkout_view():
    if request.method == 'POST':
        return place_order()

    totals = calculate_cart_totals(current_user.id)
    if not totals['items']:
        flash('Your shopping cart is empty. Add products before checking out.', 'warning')
        return redirect(url_for('cart.view_cart'))

    # Verify inventory availability before rendering checkout
    stock_issues = []
    for item in totals['items']:
        if not item.product or not item.product.is_active:
            stock_issues.append(f'Product "{item.product_id}" is no longer available.')
        elif item.quantity > item.product.stock:
            stock_issues.append(
                f'Only {item.product.stock} units available for "{item.product.name}". Please adjust quantity in cart.'
            )

    if stock_issues:
        for issue in stock_issues:
            flash(issue, 'danger')
        return redirect(url_for('cart.view_cart'))

    # Generate a fresh order token for idempotency / double-submit defense
    order_token = uuid.uuid4().hex
    session['checkout_token'] = order_token

    return render_template('checkout.html', **totals, user=current_user, order_token=order_token)


@checkout_bp.route('/place-order', methods=['POST'])
@checkout_bp.route('/place-order/', methods=['POST'])
@login_required
def place_order():
    is_json = request.is_json
    data = request.get_json(silent=True) if is_json else request.form
    if is_json and not isinstance(data, dict):
        return jsonify({'success': False, 'errors': ['Checkout data must be a JSON object.']}), 400

    errors = []

    def text_field(name, default=''):
        value = data.get(name, default)
        if not isinstance(value, str):
            errors.append(f'{name.replace("_", " ").capitalize()} must be text.')
            return ''
        return value.strip()

    full_name = text_field('full_name')
    email = text_field('email')
    phone = text_field('phone')
    shipping_address = text_field('shipping_address')
    city = text_field('city')
    postal_code = text_field('postal_code')
    payment_method = text_field('payment_method', 'Cash on Delivery')
    notes = text_field('notes')

    raw_lat = data.get('latitude')
    raw_lng = data.get('longitude')
    lat, lng, coord_err = parse_and_validate_coordinates(raw_lat, raw_lng)

    # Form validation
    if not full_name:
        errors.append('Recipient full name is required.')
    if not email:
        errors.append('Email address is required.')
    if not phone:
        errors.append('Contact phone number is required.')
    if not shipping_address:
        errors.append('Shipping delivery address is required.')
    if not city:
        errors.append('City is required.')
    if not postal_code:
        errors.append('Postal/ZIP code is required.')
    if payment_method not in {'Cash on Delivery', 'Demo Card / Net Banking'}:
        errors.append('Choose a supported payment method.')
    field_limits = {
        'full name': (full_name, 100),
        'email address': (email, 120),
        'phone': (phone, 20),
        'shipping address': (shipping_address, 1000),
        'city': (city, 64),
        'postal code': (postal_code, 20),
        'delivery notes': (notes, 2000),
    }
    errors.extend(f'{name.capitalize()} must be {limit} characters or fewer.'
                  for name, (value, limit) in field_limits.items() if len(value) > limit)
    if coord_err:
        errors.append(coord_err)

    if errors:
        if is_json:
            return jsonify({'success': False, 'errors': errors}), 400
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('checkout.checkout_view'))

    # Retrieve cart items
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        # Check if an order was placed within the last 30s (e.g. duplicate button click / double submit)
        recent_order = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).first()
        if is_order_recent(recent_order):
            msg = f'Order #{recent_order.order_number} has already been placed!'
            if is_json:
                return jsonify({
                    'success': True,
                    'message': msg,
                    'order_id': recent_order.id,
                    'order_number': recent_order.order_number,
                    'redirect_url': url_for('checkout.confirmation', order_id=recent_order.id)
                })
            flash(msg, 'info')
            return redirect(url_for('checkout.confirmation', order_id=recent_order.id))

        msg = 'Your cart is empty. Please add items before placing an order.'
        if is_json:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'warning')
        return redirect(url_for('cart.view_cart'))

    # Refresh any cached objects to verify fresh database stock
    db.session.expire_all()

    # Calculate exact totals on server (Never trust client prices)
    subtotal = Decimal('0.00')
    for item in cart_items:
        product = db.session.get(Product, item.product_id, execution_options={"populate_existing": True})
        if not product or not product.is_active:
            msg = f'Product is unavailable or deactivated.'
            if is_json:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('cart.view_cart'))
        if item.quantity > product.stock:
            msg = f'Insufficient stock for "{product.name}". Available: {product.stock}.'
            if is_json:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('cart.view_cart'))
        
        subtotal += Decimal(str(product.price)) * item.quantity

    threshold = Decimal(str(current_app.config.get('FREE_SHIPPING_THRESHOLD', 50.00)))
    standard_fee = Decimal(str(current_app.config.get('STANDARD_SHIPPING_FEE', 5.00)))
    shipping_fee = Decimal('0.00') if subtotal >= threshold else standard_fee
    grand_total = subtotal + shipping_fee

    # Atomic order creation and inventory deduction
    try:
        order = Order(
            order_number=generate_order_number(),
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
        db.session.flush()  # Obtain order.id
        record_initial_order_status(order, current_user)

        # Create OrderItems and decrement stock
        for item in cart_items:
            product = db.session.get(Product, item.product_id)
            item_subtotal = Decimal(str(product.price)) * item.quantity
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=item.quantity,
                subtotal=item_subtotal
            )
            db.session.add(order_item)

            # Reduce product inventory
            stock_update = db.session.execute(
                update(Product)
                .where(Product.id == product.id, Product.stock >= item.quantity)
                .values(stock=Product.stock - item.quantity)
            )
            if stock_update.rowcount != 1:
                raise ValueError(f'Insufficient stock for "{product.name}". Please try again.')

            # Remove item from cart
            db.session.delete(item)

        # Update default user profile info if empty
        if not current_user.phone and phone:
            current_user.phone = phone
        if not current_user.address and shipping_address:
            current_user.address = shipping_address
        if not current_user.city and city:
            current_user.city = city
        if not current_user.postal_code and postal_code:
            current_user.postal_code = postal_code

        db.session.commit()

        if is_json:
            return jsonify({
                'success': True,
                'message': 'Order placed successfully!',
                'order_id': order.id,
                'order_number': order.order_number,
                'redirect_url': url_for('checkout.confirmation', order_id=order.id)
            })

        flash(f'Order #{order.order_number} placed successfully! Thank you for your purchase.', 'success')
        return redirect(url_for('checkout.confirmation', order_id=order.id))

    except ValueError as error:
        db.session.rollback()
        if is_json:
            return jsonify({'success': False, 'message': str(error)}), 400
        flash(str(error), 'danger')
        return redirect(url_for('checkout.checkout_view'))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to place order for user %s', current_user.id)
        msg = 'An error occurred while processing your order. Please try again.'
        if is_json:
            return jsonify({'success': False, 'message': msg}), 500
        flash(msg, 'danger')
        return redirect(url_for('checkout.checkout_view'))


@checkout_bp.route('/confirmation/<int:order_id>')
@login_required
def confirmation(order_id):
    order = db.get_or_404(Order, order_id)
    # Ensure customer can only view their own order
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    return render_template('order_confirmation.html', order=order)
