from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import current_user, login_required
from ..models import Product, Category, CartItem, Order, OrderItem
from ..extensions import db

customer_bp = Blueprint('customer', __name__)


@customer_bp.route('/profile')
@login_required
def profile():
    return render_template('customer/profile.html')


@customer_bp.route('/')
def index():
    category_id = request.args.get('category', type=int)
    search = request.args.get('q', '').strip()

    query = Product.query.filter_by(is_active=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    products = query.order_by(Product.created_at.desc()).all()

    latest_products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.created_at.desc())
        .limit(5)
        .all()
    )
    categories = Category.query.filter_by(visible=True).order_by(Category.name).all()

    return render_template('customer/index.html',
                           products=products,
                           latest_products=latest_products,
                           categories=categories,
                           current_category=category_id,
                           search=search)


@customer_bp.route('/product/<slug>')
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template('customer/product.html', product=product)


@customer_bp.route('/cart')
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum((item.product.price * item.quantity for item in items), Decimal('0.00'))
    return render_template('customer/cart.html', items=items, total=total)


@customer_bp.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    qty = request.form.get('quantity', 1, type=int) or 1
    if qty < 1:
        qty = 1
    if product.stock < qty:
        flash('Not enough stock.', 'warning')
        return redirect(url_for('customer.product_detail', slug=product.slug))
    item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if item:
        item.quantity += qty
    else:
        item = CartItem(user_id=current_user.id, product_id=product.id, quantity=qty)
        db.session.add(item)
    db.session.commit()
    flash('Added to cart.', 'success')
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    qty = request.form.get('quantity', type=int)
    if qty and qty > 0:
        item.quantity = qty
        db.session.commit()
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('customer.cart'))


@customer_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('customer.index'))

    if request.method == 'POST':
        address = request.form.get('address', '').strip()
        if not address:
            flash('Shipping address is required.', 'danger')
            return render_template('customer/checkout.html', items=items)

        for item in items:
            if item.product.stock < item.quantity:
                flash(f'Not enough stock for {item.product.name}.', 'danger')
                return redirect(url_for('customer.cart'))

        total = sum((item.product.price * item.quantity for item in items), Decimal('0.00'))
        order = Order(user_id=current_user.id, status='pending',
                      total_amount=total, shipping_address=address)
        db.session.add(order)
        db.session.flush()

        for item in items:
            db.session.add(OrderItem(order_id=order.id, product_id=item.product_id,
                                     quantity=item.quantity, price_at_purchase=item.product.price))
            item.product.stock -= item.quantity
            db.session.delete(item)

        db.session.commit()
        flash(f'Order #{order.id} placed successfully!', 'success')
        return redirect(url_for('customer.order_detail', order_id=order.id))

    return render_template('customer/checkout.html', items=items)


@customer_bp.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('customer/orders.html', orders=orders)


@customer_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_staff():
        abort(403)
    return render_template('customer/order_detail.html', order=order)