import os
import click
from decimal import Decimal
from flask import Flask, render_template, jsonify, request
from flask_login import current_user
from sqlalchemy import inspect, text
from config import config_by_name
from extensions import db, login_manager, csrf
from models import (
    User, Category, Product, CartItem, Order, OrderItem,
    OrderStatusHistory, PaymentHistory, get_utc_now
)


def create_app(config_name=None):
    """Application factory for the E-Commerce web application."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.cart import cart_bp
    from routes.checkout import checkout_bp
    from routes.orders import orders_bp
    from routes.admin import admin_bp
    from routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

   
    @app.context_processor
    def inject_global_data():
        categories = []
        cart_count = 0
        try:
            categories = Category.query.all()
            if current_user.is_authenticated:
                cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
                cart_count = sum(item.quantity for item in cart_items)
        except Exception:
           
            pass
        return {
            'nav_categories': categories,
            'nav_cart_count': cart_count,
            'currency_symbol': app.config.get('CURRENCY_SYMBOL', '$'),
            'google_maps_api_key': app.config.get('GOOGLE_MAPS_API_KEY', '')
        }

    
    @app.template_filter('currency')
    def currency_filter(value):
        try:
            return f"${Decimal(str(value)):,.2f}"
        except Exception:
            return f"${value}"

    
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Resource not found'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Access forbidden'}), 403
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500

    
    register_commands(app)
    with app.app_context():
        db.create_all()


    return app


def register_commands(app):
    """Register custom Flask CLI management commands."""

    @app.cli.command('init-db')
    def init_db():
        """Create database tables."""
        db.create_all()
        click.echo('Database tables initialized successfully.')

    @app.cli.command('upgrade-order-tracking')
    def upgrade_order_tracking():
        """Add order tracking fields and history to an existing database."""
        order_columns = {
            'discount_amount': 'NUMERIC(10, 2) NOT NULL DEFAULT 0',
            'cancellation_reason': 'TEXT NULL',
            'cancelled_at': 'DATETIME NULL',
            'estimated_delivery_at': 'DATETIME NULL',
            'tracking_number': 'VARCHAR(100) NULL',
            'courier_name': 'VARCHAR(100) NULL',
            'refund_status': "VARCHAR(32) NOT NULL DEFAULT 'Not applicable'",
            'payment_confirmed_at': 'DATETIME NULL',
            'payment_confirmed_by': 'INTEGER NULL',
            'razorpay_order_id': 'VARCHAR(64) NULL',
            'razorpay_payment_id': 'VARCHAR(64) NULL',
        }
        inspector = inspect(db.engine)
        if not inspector.has_table('orders'):
            raise click.ClickException(
                'The configured database has no orders table. Verify DATABASE_URL before migrating.'
            )
        existing = {column['name'] for column in inspector.get_columns('orders')}
        preparer = db.engine.dialect.identifier_preparer
        with db.engine.begin() as connection:
            for name, column_type in order_columns.items():
                if name not in existing:
                    connection.execute(text(
                        f'ALTER TABLE orders ADD COLUMN {preparer.quote(name)} {column_type}'
                    ))

        db.metadata.create_all(
            bind=db.engine,
            tables=[
                OrderStatusHistory.__table__,
                PaymentHistory.__table__,
            ],
            checkfirst=True,
        )
        with db.engine.begin() as connection:
            connection.execute(text(
                'INSERT INTO order_status_history '
                '(order_id, status, note, actor_id, tracking_number, courier_name, created_at) '
                'SELECT o.id, o.status, :note, NULL, o.tracking_number, o.courier_name, '
                'COALESCE(o.updated_at, o.created_at, CURRENT_TIMESTAMP) '
                'FROM orders AS o '
                'WHERE NOT EXISTS ('
                'SELECT 1 FROM order_status_history AS h WHERE h.order_id = o.id'
                ')'
            ), {'note': 'Status captured during order tracking schema migration'})
        click.echo(
            f'Order tracking schema upgraded in {db.engine.url.database}; '
            'existing orders and their current status have been preserved.'
        )

    @app.cli.command('seed-db')
    def seed_db():
        """Populate database with categories, realistic products, and demo accounts."""
        from seed import run_seed
        run_seed()
        click.echo('Database populated with sample data.')

    @app.cli.command('create-admin')
    @click.option('--username', prompt=True, help='Administrator username')
    @click.option('--email', prompt=True, help='Administrator email')
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Administrator password')
    def create_admin(username, email, password):
        """Create an administrative account securely via CLI."""
        existing = User.query.filter((User.username == username) | (User.email == email.lower())).first()
        if existing:
            click.echo(f'Error: User with username "{username}" or email "{email}" already exists.')
            return

        admin = User(
            username=username.strip(),
            email=email.strip().lower(),
            full_name='System Administrator',
            role='admin'
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f'Admin account "{username}" created successfully!')



app = create_app()

if __name__ == '__main__':
    
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
