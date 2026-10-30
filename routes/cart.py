from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Product, CartItem

cart_bp = Blueprint('cart', __name__, url_prefix='/cart')


def calculate_cart_totals(user_id: int):
    """Calculate cart subtotal, shipping, and grand total."""
    items = CartItem.query.filter_by(user_id=user_id).all()
    subtotal = Decimal('0.00')
    total_items = 0

    for item in items:
        if item.product and item.product.is_active:
            subtotal += Decimal(str(item.product.price)) * item.quantity
            total_items += item.quantity

    threshold = Decimal(str(current_app.config.get('FREE_SHIPPING_THRESHOLD', 50.00)))
    standard_fee = Decimal(str(current_app.config.get('STANDARD_SHIPPING_FEE', 5.00)))

    shipping_fee = Decimal('0.00') if subtotal >= threshold or subtotal == 0 else standard_fee
    grand_total = subtotal + shipping_fee

    return {
        'items': items,
        'subtotal': subtotal,
        'shipping_fee': shipping_fee,
        'grand_total': grand_total,
        'total_items': total_items,
        'free_shipping_eligible': subtotal >= threshold
    }


@cart_bp.route('')
@cart_bp.route('/')
def view_cart():
    if not current_user.is_authenticated:
        return render_template(
            'cart.html',
            items=[],
            subtotal=Decimal('0.00'),
            shipping_fee=Decimal('0.00'),
            grand_total=Decimal('0.00'),
            total_items=0,
            free_shipping_eligible=False
        )
    cart_summary = calculate_cart_totals(current_user.id)
    return render_template('cart.html', **cart_summary)


@cart_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_to_cart():
    if request.method == 'GET':
        return redirect(url_for('cart.view_cart'))

    is_json = request.is_json
    data = request.get_json(silent=True) or request.form

    try:
        product_id = int(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
    except (ValueError, TypeError):
        message = 'Invalid product or quantity specified.'
        if is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'danger')
        return redirect(request.referrer or url_for('main.products'))

    if quantity <= 0:
        message = 'Quantity must be greater than zero.'
        if is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'warning')
        return redirect(request.referrer or url_for('main.products'))

    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        message = 'Product not found or is currently unavailable.'
        if is_json:
            return jsonify({'success': False, 'message': message}), 404
        flash(message, 'danger')
        return redirect(request.referrer or url_for('main.products'))

    # Check available stock
    if product.stock <= 0:
        message = f'Sorry, "{product.name}" is currently out of stock.'
        if is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'warning')
        return redirect(request.referrer or url_for('main.product_detail', product_id=product_id))

    existing_item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    new_quantity = quantity if not existing_item else existing_item.quantity + quantity

    if new_quantity > product.stock:
        message = f'Cannot add {quantity} more. Only {product.stock} items in stock (you already have {existing_item.quantity if existing_item else 0} in cart).'
        if is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'warning')
        return redirect(request.referrer or url_for('main.product_detail', product_id=product_id))

    if existing_item:
        existing_item.quantity = new_quantity
    else:
        new_item = CartItem(user_id=current_user.id, product_id=product.id, quantity=quantity)
        db.session.add(new_item)

    db.session.commit()

    # Get updated total items in cart
    totals = calculate_cart_totals(current_user.id)
    success_message = f'"{product.name}" added to your cart!'

    action_type = data.get('action') or ('buy_now' if data.get('buy_now') else 'add')
    if action_type == 'buy_now':
        if is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': success_message,
                'cart_count': totals['total_items'],
                'subtotal': float(totals['subtotal']),
                'grand_total': float(totals['grand_total']),
                'redirect_url': url_for('checkout.checkout_view')
            })
        return redirect(url_for('checkout.checkout_view'))

    if is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': success_message,
            'cart_count': totals['total_items'],
            'subtotal': float(totals['subtotal']),
            'grand_total': float(totals['grand_total'])
        })

    flash(success_message, 'success')
    return redirect(request.referrer or url_for('cart.view_cart'))


@cart_bp.route('/update/<int:item_id>', methods=['POST'])
@login_required
def update_quantity(item_id):
    cart_item = db.get_or_404(CartItem, item_id)
    if cart_item.user_id != current_user.id:
        abort(403)

    is_json = request.is_json
    data = request.get_json(silent=True) or request.form

    action = data.get('action')  # 'increase', 'decrease', or direct 'quantity'
    
    if action == 'increase':
        new_quantity = cart_item.quantity + 1
    elif action == 'decrease':
        new_quantity = cart_item.quantity - 1
    else:
        try:
            new_quantity = int(data.get('quantity', cart_item.quantity))
        except (ValueError, TypeError):
            new_quantity = cart_item.quantity

    if new_quantity <= 0:
        db.session.delete(cart_item)
        db.session.commit()
        totals = calculate_cart_totals(current_user.id)
        msg = 'Item removed from your cart.'
        if is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': msg,
                'item_removed': True,
                'item_id': item_id,
                'cart_count': totals['total_items'],
                'subtotal': float(totals['subtotal']),
                'shipping_fee': float(totals['shipping_fee']),
                'grand_total': float(totals['grand_total'])
            })
        flash(msg, 'info')
        return redirect(url_for('cart.view_cart'))

    # Validate against product stock
    if new_quantity > cart_item.product.stock:
        msg = f'Maximum available stock for "{cart_item.product.name}" is {cart_item.product.stock}.'
        if is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'warning')
        return redirect(url_for('cart.view_cart'))

    cart_item.quantity = new_quantity
    db.session.commit()

    totals = calculate_cart_totals(current_user.id)
    if is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Quantity updated.',
            'item_id': item_id,
            'quantity': cart_item.quantity,
            'item_subtotal': float(cart_item.subtotal),
            'cart_count': totals['total_items'],
            'subtotal': float(totals['subtotal']),
            'shipping_fee': float(totals['shipping_fee']),
            'grand_total': float(totals['grand_total'])
        })

    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_item(item_id):
    cart_item = db.get_or_404(CartItem, item_id)
    if cart_item.user_id != current_user.id:
        abort(403)

    product_name = cart_item.product.name if cart_item.product else 'Item'
    db.session.delete(cart_item)
    db.session.commit()

    totals = calculate_cart_totals(current_user.id)
    msg = f'"{product_name}" removed from cart.'

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': msg,
            'cart_count': totals['total_items'],
            'subtotal': float(totals['subtotal']),
            'shipping_fee': float(totals['shipping_fee']),
            'grand_total': float(totals['grand_total'])
        })

    flash(msg, 'info')
    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/clear', methods=['POST'])
@login_required
def clear_cart():
    CartItem.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash('Your cart has been cleared.', 'info')
    return redirect(url_for('cart.view_cart'))
