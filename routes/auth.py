import re
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def admin_required(f):
    """Decorator to restrict access to administrator users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in with administrator privileges.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return bool(re.match(pattern, email))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        if not is_valid_email(email):
            errors.append('Please provide a valid email address.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters long.')
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if User.query.filter_by(username=username).first():
            errors.append('Username is already taken. Please choose another.')
        if User.query.filter_by(email=email).first():
            errors.append('An account with this email already exists.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html', username=username, email=email, full_name=full_name)

        # Create user - explicitly always default to role 'user'
        user = User(
            username=username,
            email=email,
            full_name=full_name or username,
            role='user'
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Account created successfully! Welcome to ShopFlow.', 'success')
        return redirect(url_for('main.index'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        login_identifier = request.form.get('username_or_email', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not login_identifier or not password:
            flash('Please enter both your username/email and password.', 'warning')
            return render_template('auth/login.html', login_identifier=login_identifier)

        # Search by username or email
        user = User.query.filter(
            (User.username == login_identifier) | (User.email == login_identifier.lower())
        ).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.full_name or user.username}!', 'success')
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username/email or password. Please try again.', 'danger')
            return render_template('auth/login.html', login_identifier=login_identifier)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out successfully.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        postal_code = request.form.get('postal_code', '').strip()

        # Optional password update
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')

        if new_password:
            if not current_password or not current_user.check_password(current_password):
                flash('Current password is incorrect.', 'danger')
                return render_template('auth/profile.html')
            if len(new_password) < 6:
                flash('New password must be at least 6 characters.', 'danger')
                return render_template('auth/profile.html')
            current_user.set_password(new_password)

        current_user.full_name = full_name or current_user.full_name
        current_user.phone = phone
        current_user.address = address
        current_user.city = city
        current_user.postal_code = postal_code

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))

    recent_orders = current_user.orders.order_by(db.desc('created_at')).limit(5).all()
    return render_template('auth/profile.html', user=current_user, recent_orders=recent_orders)
