from flask import Blueprint, render_template, request, abort
from extensions import db
from models import Product, Category

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    categories = Category.query.all()
    featured_products = Product.query.filter_by(is_active=True, is_featured=True).limit(8).all()
    if not featured_products:
        # Fallback to any active products if none marked featured yet
        featured_products = Product.query.filter_by(is_active=True).limit(8).all()
    
    new_arrivals = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(4).all()
    return render_template('index.html', categories=categories, featured_products=featured_products, new_arrivals=new_arrivals)


@main_bp.route('/products')
def products():
    category_slug = request.args.get('category', '').strip()
    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'newest').strip()
    stock_filter = request.args.get('stock', '').strip()

    query = Product.query.filter_by(is_active=True)

    selected_category = None
    if category_slug:
        selected_category = Category.query.filter_by(slug=category_slug).first()
        if selected_category:
            query = query.filter(Product.category_id == selected_category.id)

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            (Product.name.ilike(search_pattern)) | (Product.description.ilike(search_pattern))
        )

    if stock_filter == 'in_stock':
        query = query.filter(Product.stock > 0)

    # Sorting
    if sort_by == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'name':
        query = query.order_by(Product.name.asc())
    else:  # newest
        query = query.order_by(Product.created_at.desc())

    products_list = query.all()
    categories = Category.query.all()

    return render_template(
        'products.html',
        products=products_list,
        categories=categories,
        selected_category=selected_category,
        search_query=search_query,
        sort_by=sort_by,
        stock_filter=stock_filter,
        total_results=len(products_list)
    )


@main_bp.route('/products/<int:product_id>')
def product_detail(product_id):
    product = db.get_or_404(Product, product_id)
    if not product.is_active:
        abort(404)

    related_products = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()

    return render_template('product_detail.html', product=product, related_products=related_products)


@main_bp.route('/about')
def about():
    return render_template('about.html')


@main_bp.route('/contact')
def contact():
    return render_template('contact.html')
