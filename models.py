from datetime import datetime, timezone
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager


def get_utc_now():
    """Return timezone-aware or clean UTC datetime."""
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)  # 'user' or 'admin'
    full_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(64), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    # Relationships
    orders = db.relationship(
    'Order',
    back_populates='user',
    foreign_keys='Order.user_id',
    lazy='dynamic',
    cascade='all, delete-orphan'
)
    cart_items = db.relationship('CartItem', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'full_name': self.full_name,
            'phone': self.phone,
            'address': self.address,
            'city': self.city,
            'postal_code': self.postal_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(64), default='bi-tag', nullable=False)

    products = db.relationship('Product', back_populates='category', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'icon': self.icon,
            'product_count': self.products.count()
        }


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)

    category = db.relationship('Category', back_populates='products')
    cart_items = db.relationship('CartItem', back_populates='product', cascade='all, delete-orphan')

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.stock <= 5

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': float(self.price),
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'image_url': self.image_url,
            'stock': self.stock,
            'in_stock': self.in_stock,
            'is_featured': self.is_featured,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=get_utc_now)

    user = db.relationship('User', back_populates='cart_items')
    product = db.relationship('Product', back_populates='cart_items')

    @property
    def subtotal(self) -> Decimal:
        if self.product:
            return Decimal(str(self.product.price)) * self.quantity
        return Decimal('0.00')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'product': self.product.to_dict() if self.product else None,
            'quantity': self.quantity,
            'subtotal': float(self.subtotal),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Order(db.Model):
    __tablename__ = 'orders'

    STATUS_CHOICES = ['Order Placed', 'Confirmed', 'Shipped', 'Delivered', 'Cancelled']

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Customer and shipping information
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    shipping_address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(64), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False)

    # Delivery geolocation coordinates (Google Maps integration)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Financial details
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    shipping_fee = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    
        # Payment & delivery status
    payment_method = db.Column(db.String(32), default='Cash on Delivery', nullable=False)
    payment_status = db.Column(db.String(32), default='Pending', nullable=False)
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)
    payment_confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Razorpay gateway references
    razorpay_order_id = db.Column(db.String(64), unique=True, nullable=True)
    razorpay_payment_id = db.Column(db.String(64), unique=True, nullable=True)

    status = db.Column(db.String(32), default='Order Placed', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    estimated_delivery_at = db.Column(db.DateTime, nullable=True)
    tracking_number = db.Column(db.String(100), nullable=True)
    courier_name = db.Column(db.String(100), nullable=True)
    refund_status = db.Column(db.String(32), default='Not applicable', nullable=False)

    created_at = db.Column(db.DateTime, default=get_utc_now)
    updated_at = db.Column(db.DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Relationships
    user = db.relationship('User', back_populates='orders',
    foreign_keys=[user_id])
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    status_history = db.relationship(
        'OrderStatusHistory', back_populates='order', cascade='all, delete-orphan',
        order_by='OrderStatusHistory.created_at'
    )

    payment_history = db.relationship(
        'PaymentHistory',
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='PaymentHistory.created_at'
    )

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def google_maps_url(self) -> str:
        """Return a direct Google Maps destination URL."""
        if self.has_coordinates:
            return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        import urllib.parse
        addr = f"{self.shipping_address}, {self.city}, {self.postal_code}"
        return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(addr)}"

    @property
    def status_badge(self) -> str:
        mapping = {
            'Order Placed': 'bg-warning text-dark',
            'Pending': 'bg-warning text-dark',
            'Confirmed': 'bg-info text-dark',
            'Shipped': 'bg-primary text-white',
            'Delivered': 'bg-success text-white',
            'Cancelled': 'bg-danger text-white'
        }
        return mapping.get(self.status, 'bg-secondary text-white')

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'user_id': self.user_id,
            'customer_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
            'shipping_address': self.shipping_address,
            'city': self.city,
            'postal_code': self.postal_code,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'has_coordinates': self.has_coordinates,
            'google_maps_url': self.google_maps_url,
            'payment_method': self.payment_method,
            'payment_status': self.payment_status,
            'status': self.status,
            'subtotal': float(self.subtotal),
            'discount_amount': float(self.discount_amount or 0),
            'shipping_fee': float(self.shipping_fee),
            'total_amount': float(self.total_amount),
            'tracking_number': self.tracking_number,
            'courier_name': self.courier_name,
            'refund_status': self.refund_status,
            'cancellation_reason': self.cancellation_reason,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
            'estimated_delivery_at': self.estimated_delivery_at.isoformat() if self.estimated_delivery_at else None,
            'notes': self.notes,
            'items': [item.to_dict() for item in self.items],
            'status_history': [event.to_dict() for event in self.status_history],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class OrderStatusHistory(db.Model):
    __tablename__ = 'order_status_history'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False)
    note = db.Column(db.Text, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    tracking_number = db.Column(db.String(100), nullable=True)
    courier_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=get_utc_now, nullable=False)

    order = db.relationship('Order', back_populates='status_history')
    actor = db.relationship('User')

    def to_dict(self):
        return {
            'status': self.status,
            'note': self.note,
            'tracking_number': self.tracking_number,
            'courier_name': self.courier_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

class PaymentHistory(db.Model):
    __tablename__ = 'payment_history'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True
    )
    previous_status = db.Column(db.String(32), nullable=False)
    new_status = db.Column(db.String(32), nullable=False)
    note = db.Column(db.Text, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_utc_now, nullable=False)

    order = db.relationship('Order', back_populates='payment_history')
    actor = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'previous_status': self.previous_status,
            'new_status': self.new_status,
            'note': self.note,
            'actor_id': self.actor_id,
            'created_at': (
                self.created_at.isoformat() if self.created_at else None
            ),
        }


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    product_name = db.Column(db.String(128), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'price': float(self.price),
            'quantity': self.quantity,
            'subtotal': float(self.subtotal),
        }
