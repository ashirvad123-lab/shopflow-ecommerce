from decimal import Decimal
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy import func
from extensions import db
from models import (
    User, Product, Category, Order, OrderItem,
    PaymentHistory, get_utc_now
)
from routes.auth import admin_required
from services.order_tracking import allowed_order_statuses, transition_order

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
@login_required
@admin_required
def require_admin_access():
    """Ensure every route in this blueprint requires authenticated administrator privileges."""
    pass


@admin_bp.route('/')
@admin_bp.route('/dashboard')
def dashboard():
    total_products = Product.query.count()
    low_stock_count = Product.query.filter(Product.stock <= 5, Product.is_active == True).count()
    total_orders = Order.query.count()
    total_customers = User.query.filter_by(role='user').count()

   
    revenue_result = db.session.query(func.sum(Order.total_amount)).filter(Order.status != 'Cancelled').scalar()
    total_revenue = Decimal(str(revenue_result or 0.00))

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    low_stock_products = Product.query.filter(Product.stock <= 5, Product.is_active == True).limit(5).all()

    return render_template(
        'admin/dashboard.html',
        total_products=total_products,
        low_stock_count=low_stock_count,
        total_orders=total_orders,
        total_customers=total_customers,
        total_revenue=total_revenue,
        recent_orders=recent_orders,
        low_stock_products=low_stock_products
    )


# ==========================================
# Product Management
# ==========================================

@admin_bp.route('/products')
def products():
    search_query = request.args.get('search', '').strip()
    category_id = request.args.get('category_id', type=int)
    stock_status = request.args.get('stock', '').strip()

    query = Product.query

    if search_query:
        query = query.filter(Product.name.ilike(f"%{search_query}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if stock_status == 'out':
        query = query.filter(Product.stock == 0)
    elif stock_status == 'low':
        query = query.filter(Product.stock > 0, Product.stock <= 5)

    products_list = query.order_by(Product.created_at.desc()).all()
    categories = Category.query.all()

    return render_template(
        'admin/products.html',
        products=products_list,
        categories=categories,
        search_query=search_query,
        selected_category_id=category_id,
        stock_status=stock_status
    )


@admin_bp.route('/products/new', methods=['GET', 'POST'])
def add_product():
    categories = Category.query.all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        category_id = request.form.get('category_id', type=int)
        image_url = request.form.get('image_url', '').strip()
        stock = request.form.get('stock', type=int, default=0)
        is_featured = bool(request.form.get('is_featured'))

        errors = []
        if not name:
            errors.append('Product name is required.')
        if not description:
            errors.append('Product description is required.')
        if not category_id or not db.session.get(Category, category_id):
            errors.append('Valid product category is required.')
        try:
            price_val = Decimal(price)
            if price_val < 0:
                errors.append('Price must be greater than or equal to 0.')
        except Exception:
            errors.append('Valid price is required.')

        if stock < 0:
            errors.append('Stock cannot be negative.')

        # Default fallback image if none provided
        if not image_url:
            image_url = 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80'

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/product_form.html', categories=categories, product=None)

        new_product = Product(
            name=name,
            description=description,
            price=Decimal(price),
            category_id=category_id,
            image_url=image_url,
            stock=stock,
            is_featured=is_featured,
            is_active=True
        )
        db.session.add(new_product)
        db.session.commit()

        flash(f'Product "{new_product.name}" created successfully!', 'success')
        return redirect(url_for('admin.products'))

    return render_template('admin/product_form.html', categories=categories, product=None)


@admin_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
def edit_product(product_id):
    product = db.get_or_404(Product, product_id)
    categories = Category.query.all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        category_id = request.form.get('category_id', type=int)
        image_url = request.form.get('image_url', '').strip()
        stock = request.form.get('stock', type=int, default=product.stock)
        is_featured = bool(request.form.get('is_featured'))
        is_active = bool(request.form.get('is_active'))

        errors = []
        if not name:
            errors.append('Product name is required.')
        if not description:
            errors.append('Product description is required.')
        if not category_id or not db.session.get(Category, category_id):
            errors.append('Valid category is required.')
        try:
            price_val = Decimal(price)
            if price_val < 0:
                errors.append('Price must be greater than or equal to 0.')
        except Exception:
            errors.append('Valid price is required.')

        if stock < 0:
            errors.append('Stock cannot be negative.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/product_form.html', categories=categories, product=product)

        product.name = name
        product.description = description
        product.price = Decimal(price)
        product.category_id = category_id
        if image_url:
            product.image_url = image_url
        product.stock = stock
        product.is_featured = is_featured
        product.is_active = is_active

        db.session.commit()
        flash(f'Product "{product.name}" updated successfully!', 'success')
        return redirect(url_for('admin.products'))

    return render_template('admin/product_form.html', categories=categories, product=product)


@admin_bp.route('/products/<int:product_id>/stock', methods=['POST'])
def update_stock(product_id):
    product = db.get_or_404(Product, product_id)
    try:
        new_stock = int(request.form.get('stock', product.stock))
        if new_stock < 0:
            flash('Stock quantity cannot be negative.', 'danger')
        else:
            product.stock = new_stock
            db.session.commit()
            flash(f'Stock updated to {new_stock} for "{product.name}".', 'success')
    except (ValueError, TypeError):
        flash('Invalid stock number provided.', 'danger')

    return redirect(request.referrer or url_for('admin.products'))


@admin_bp.route('/products/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    product = db.get_or_404(Product, product_id)
    product_name = product.name
    
    has_orders = OrderItem.query.filter_by(product_id=product.id).first() is not None

    if has_orders:
       
        product.is_active = False
        product.stock = 0
        db.session.commit()
        flash(f'Product "{product_name}" is associated with existing orders. It has been deactivated and hidden from storefront.', 'info')
    else:
        db.session.delete(product)
        db.session.commit()
        flash(f'Product "{product_name}" was permanently removed.', 'success')

    return redirect(url_for('admin.products'))


# ==========================================
# Order Management
# ==========================================

@admin_bp.route('/orders')
def orders():
    status_filter = request.args.get('status', '').strip()
    search_query = request.args.get('search', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    query = Order.query.join(User, Order.user_id == User.id)

    if status_filter in Order.STATUS_CHOICES:
        query = query.filter(Order.status == status_filter)
    else:
        status_filter = ''

    if search_query:
        query = query.filter(
            (Order.order_number.ilike(f"%{search_query}%")) |
            (Order.full_name.ilike(f"%{search_query}%")) |
            (Order.email.ilike(f"%{search_query}%")) |
            (User.username.ilike(f"%{search_query}%"))
        )

    try:
        if start_date:
            query = query.filter(Order.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(Order.created_at < datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('Use valid dates in YYYY-MM-DD format.', 'warning')
        start_date = ''
        end_date = ''

    pagination = query.order_by(Order.created_at.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=20, error_out=False
    )
    return render_template(
        'admin/orders.html',
        orders=pagination.items,
        pagination=pagination,
        statuses=Order.STATUS_CHOICES,
        status_filter=status_filter,
        search_query=search_query,
        start_date=start_date,
        end_date=end_date,
        next_statuses={order.id: allowed_order_statuses(order.status) for order in pagination.items},
    )


@admin_bp.route('/orders/<int:order_id>')
def order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    return render_template(
        'admin/order_detail.html',
        order=order,
        statuses=allowed_order_statuses(order.status),
    )


@admin_bp.route('/orders/<int:order_id>/status', methods=['POST'])
def update_order_status(order_id):
    order = db.get_or_404(Order, order_id)
    new_status = request.form.get('status', '').strip()
    reason = request.form.get('reason', '').strip()
    tracking_number = request.form.get('tracking_number', '').strip()
    courier_name = request.form.get('courier_name', '').strip()
    if len(tracking_number) > 100 or len(courier_name) > 100:
        flash('Tracking number and courier name must be 100 characters or fewer.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order.id))
    try:
        transition_order(
            order,
            new_status,
            actor=current_user,
            note=reason or None,
            tracking_number=tracking_number,
            courier_name=courier_name,
        )
        db.session.commit()
        flash(f'Order #{order.order_number} status updated to "{new_status}".', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update order status for %s', order.order_number)
        flash('The order status could not be updated. Please try again.', 'danger')
    return redirect(url_for('admin.order_detail', order_id=order.id))



@admin_bp.route('/orders/<int:order_id>/payment/confirm', methods=['POST'])
def confirm_cod_payment(order_id):
    order = db.get_or_404(Order, order_id)

    # Only Cash on Delivery orders can be confirmed manually.
    payment_method = (order.payment_method or '').strip().lower()
    if payment_method not in ('cash on delivery', 'cod'):
        flash('Manual payment confirmation is only for COD orders.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order.id))

    # Prevent duplicate confirmations.
    if (order.payment_status or '').strip().lower() == 'paid':
        flash('This order payment has already been confirmed.', 'info')
        return redirect(url_for('admin.order_detail', order_id=order.id))

    old_status = order.payment_status or 'Pending'

    try:
        order.payment_status = 'Paid'
        order.payment_confirmed_at = get_utc_now()
        order.payment_confirmed_by = current_user.id

        history = PaymentHistory(
            order_id=order.id,
            previous_status=old_status,
            new_status='Paid',
            note='COD payment manually confirmed by admin',
            actor_id=current_user.id,
        )
        db.session.add(history)
        db.session.commit()

        flash(f'COD payment for order #{order.order_number} marked as Paid.', 'success')

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Failed to confirm COD payment for order %s', order.order_number
        )
        flash('Payment confirmation failed. Please try again.', 'danger')

    return redirect(url_for('admin.order_detail', order_id=order.id))


# ==========================================
# User Management
# ==========================================

@admin_bp.route('/users')
def users():
    search_query = request.args.get('search', '').strip()
    query = User.query

    if search_query:
        query = query.filter(
            (User.username.ilike(f"%{search_query}%")) |
            (User.email.ilike(f"%{search_query}%")) |
            (User.full_name.ilike(f"%{search_query}%"))
        )

    all_users = query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users, search_query=search_query)
