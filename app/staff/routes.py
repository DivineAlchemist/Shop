from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import Product, Category, Order
from ..extensions import db
from ..decorators import staff_required
from ..utils import slugify

staff_bp = Blueprint('staff', __name__)


@staff_bp.route('/')
@login_required
@staff_required
def dashboard():
    total_products = Product.query.count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.status != 'cancelled').scalar()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template('panel/dashboard.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           revenue=revenue,
                           recent_orders=recent_orders)


@staff_bp.route('/products')
@login_required
@staff_required
def products():
    all_products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('panel/products.html', products=all_products)


@staff_bp.route('/products/new', methods=['GET', 'POST'])
@login_required
@staff_required
def product_new():
    categories = Category.query.order_by(Category.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', type=float)
        stock = request.form.get('stock', type=int, default=0)
        description = request.form.get('description', '').strip()
        image_url = request.form.get('image_url', '').strip()
        category_id = request.form.get('category_id', type=int)

        if not name or price is None:
            flash('Name and price are required.', 'danger')
        else:
            slug = slugify(name) or 'product'
            base, i = slug, 1
            while Product.query.filter_by(slug=slug).first():
                slug = f'{base}-{i}'
                i += 1
            product = Product(name=name, slug=slug, price=price, stock=stock or 0,
                              description=description, image_url=image_url,
                              category_id=category_id or None)
            db.session.add(product)
            db.session.commit()
            flash('Product created.', 'success')
            return redirect(url_for('staff.products'))
    return render_template('panel/product_form.html', product=None, categories=categories)


@staff_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.order_by(Category.name).all()
    if request.method == 'POST':
        product.name = request.form.get('name', '').strip() or product.name
        product.price = request.form.get('price', type=float) or product.price
        product.stock = request.form.get('stock', type=int, default=product.stock)
        product.description = request.form.get('description', '').strip()
        product.image_url = request.form.get('image_url', '').strip()
        product.category_id = request.form.get('category_id', type=int) or None
        product.is_active = bool(request.form.get('is_active'))
        db.session.commit()
        flash('Product updated.', 'success')
        return redirect(url_for('staff.products'))
    return render_template('staff/product_form.html', product=product, categories=categories)


@staff_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@staff_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted.', 'info')
    return redirect(url_for('staff.products'))

@staff_bp.route('/categories')
@login_required
@staff_required
def categories():
    all_categories = Category.query.order_by(Category.name).all()
    return render_template('panel/categories.html', categories=all_categories)


@staff_bp.route('/categories/new', methods=['GET', 'POST'])
@login_required
@staff_required
def category_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        visible = request.form.get('visible') == 'on'

        if not name:
            flash('Name is required.', 'danger')
        else:
            slug = slugify(name) or 'category'
            base, i = slug, 1
            while Category.query.filter_by(slug=slug).first():
                slug = f'{base}-{i}'
                i += 1
            db.session.add(Category(name=name, slug=slug, visible=visible))
            db.session.commit()
            flash('Category created.', 'success')
            return redirect(url_for('staff.categories'))
    return render_template('panel/category_form.html', category=None)


@staff_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def category_edit(category_id):
    category = Category.query.get_or_404(category_id)
    if request.method == 'POST':
        category.name = request.form.get('name', '').strip() or category.name
        category.visible = request.form.get('visible') == 'on'
        db.session.commit()
        flash('Category updated.', 'success')
        return redirect(url_for('staff.categories'))
    return render_template('panel/category_form.html', category=category)


@staff_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@staff_required
def category_delete(category_id):
    category = Category.query.get_or_404(category_id)
    if category.products:
        flash('Cannot delete a category that has products.', 'danger')
        return redirect(url_for('staff.categories'))
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted.', 'info')
    return redirect(url_for('staff.categories'))

@staff_bp.route('/orders')
@login_required
@staff_required
def orders():
    status = request.args.get('status')
    query = Order.query
    if status:
        query = query.filter_by(status=status)
    all_orders = query.order_by(Order.created_at.desc()).all()
    return render_template('panel/orders.html', orders=all_orders, current_status=status)


@staff_bp.route('/orders/<int:order_id>', methods=['GET', 'POST'])
@login_required
@staff_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if request.method == 'POST':
        new_status = request.form.get('status')
        if new_status in ('pending', 'processing', 'shipped', 'delivered', 'cancelled'):
            order.status = new_status
            db.session.commit()
            flash('Order status updated.', 'success')
        return redirect(url_for('staff.order_detail', order_id=order.id))
    return render_template('panel/order_detail.html', order=order)