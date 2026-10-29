import json
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash, request, abort, current_app,
                   make_response)
from flask_login import current_user, login_required
from sqlalchemy import func

from ..models import (Product, ProductVariant, Category, CartItem, Order, OrderItem, Address, WishlistItem,
                      Review, ShippingMethod)
from ..extensions import db, csrf
from ..i18n import flash  # translated flash messages
from ..services import catalog as svc, pricing, orders as order_service
from ..services.catalog import CatalogFilters, SORT_LABELS
from ..services.notifications import set_marketing_consent, apply_optout
from ..services.products import combo_key
from ..utils import normalize_phone

customer_bp = Blueprint('customer', __name__)
FILTER_KEYS = ('q', 'category', 'cat', 'cat', 'tag', 'min_price', 'max_price', 'sort', 'page', 'in_stock')


def _staff_preview():
    return bool(current_user.is_authenticated and current_user.is_staff() and request.args.get('internal') == '1')


# ------------------------------------------------------------------ profile / consent
@customer_bp.route('/profile')
@login_required
def profile():
    return render_template('customer/profile.html')


@customer_bp.route('/profile/marketing', methods=['POST'])
@login_required
def profile_marketing():
    set_marketing_consent(current_user, request.form.get('consent') == 'on')
    flash('SMS preferences updated.', 'success')
    return redirect(url_for('customer.profile'))


@customer_bp.route('/sms/optout/<token>', methods=['GET', 'POST'])
@csrf.exempt  # the signed token is the authorization
def sms_optout(token):
    if request.method == 'POST':
        ok = apply_optout(token)
        return render_template('customer/optout.html', done=ok, invalid=not ok)
    return render_template('customer/optout.html', done=False, invalid=False)


# ------------------------------------------------------------------ home / catalog
@customer_bp.route('/')
def index():
    args = request.args
    if any(k in args for k in FILTER_KEYS) or any(k.startswith(('a_', 'opt_')) for k in args):
        rest = {k: v for k, v in args.lists() if k != 'category'}
        legacy = args.get('category', type=int)  # old links used ?category=<id>
        cat = svc.get_category(id=legacy) if legacy else None
        if cat:
            return redirect(url_for('customer.category', slug=cat.slug, **rest))
        return redirect(url_for('customer.catalog', **rest))
    sections = svc.homepage_sections()
    top = [n['category'] for n in svc.category_tree(public_only=True)]
    return render_template('customer/index.html', sections=sections, banners=svc.active_banners(), categories=top)


@customer_bp.route('/categories')
def categories():
    """Full category tree (unlimited depth) - only publicly visible categories."""
    return render_template('customer/categories.html', tree=svc.category_tree(public_only=True))


def _chips(f, facets):
    """Active filters as removable chips: [(label, url_without_this_filter)]."""
    args = {k: list(v) for k, v in request.args.lists() if k != 'page'}
    base = dict(request.view_args or {})

    def url_without(key, value=None):
        a = {k: list(v) for k, v in args.items()}
        if value is None:
            a.pop(key, None)
        else:
            a[key] = [x for x in a.get(key, []) if x != value]
            if not a[key]:
                a.pop(key)
        return url_for(request.endpoint, **base, **a)
    chips = []
    for c in f.cats:
        chips.append((c.name, url_without('cat', c.slug)))
    if f.q:
        chips.append((f'"{f.q}"', url_without('q')))
    tag_names = {slug: name for slug, name, _ in facets['tags']}
    for t in f.tags:
        chips.append((tag_names.get(t, t), url_without('tag', t)))
    for (aslug, aname), vals in facets['attrs'].items():
        labels = {v: l for v, l, _ in vals}
        for v in f.attrs.get(aslug, []):
            chips.append((f'{aname}: {labels.get(v, v)}', url_without('a_' + aslug, v)))
    for g, vals in facets['options'].items():
        labels = {k: l for k, l, _ in vals}
        for v in f.options.get(g, []):
            chips.append((f'{g}: {labels.get(v, v)}', url_without('opt_' + g, v)))
    if f.min_price is not None:
        chips.append((f'From {f.min_price:g}', url_without('min_price')))
    if f.max_price is not None:
        chips.append((f'Up to {f.max_price:g}', url_without('max_price')))
    if f.in_stock:
        chips.append(('In stock', url_without('in_stock')))
    return chips


def _render_catalog(category=None):
    include_internal = _staff_preview()
    f = CatalogFilters.from_args(request.args, category=category, include_internal=include_internal,
                                 per_page=current_app.config['PRODUCTS_PER_PAGE'])
    page = svc.search_products(f)
    children = [c for c in category.children if c.public_effective or include_internal] if category else []
    facets = svc.facets(f)
    selected = list(f.cats) or ([category] if category else [])
    open_ids = {int(i) for c in selected for i in (c.path or '').strip('/').split('/') if i}
    return render_template('customer/catalog.html', page=page, f=f, facets=facets, category=category,
                           chips=_chips(f, facets), children=children, selected_cat_slugs={c.slug for c in selected},
                           open_cat_ids=open_ids, cat_tree=svc.category_tree(public_only=not include_internal), crumbs=svc.breadcrumbs(category), sorts=SORT_LABELS,
                           args_no_page={k: v for k, v in request.args.lists() if k != 'page'}, search=f.q)


@customer_bp.route('/shop')
def catalog():
    return _render_catalog(None)


@customer_bp.route('/category/<slug>')
def category(slug):
    cat = svc.get_category(slug=slug, allow_internal=_staff_preview())
    if cat is None:
        abort(404)
    return _render_catalog(cat)


@customer_bp.route('/product/<slug>')
def product_detail(slug):
    product = svc.product_by_slug(slug, include_internal=_staff_preview())
    if product is None:
        abort(404)
    crumb_cat = product.category if (product.category and product.category.public_effective) else next(
        (c for c in product.categories if c.public_effective), None)
    variants = {v.option_key: dict(id=v.id, available=v.available, price=str(v.unit_price),
                                   base=str(v.base_price), sku=v.sku or '')
                for v in product.active_variants}
    reviews = (Review.query.filter_by(product_id=product.id, is_approved=True)
               .order_by(Review.created_at.desc()).limit(20).all())
    avg = db.session.query(func.avg(Review.rating)).filter_by(product_id=product.id, is_approved=True).scalar()
    in_wishlist = bool(current_user.is_authenticated and WishlistItem.query.filter_by(
        user_id=current_user.id, product_id=product.id).first())
    return render_template('customer/product.html', product=product, crumbs=svc.breadcrumbs(crumb_cat),
                           variants_json=json.dumps(variants), reviews=reviews,
                           avg_rating=round(float(avg), 1) if avg else None, in_wishlist=in_wishlist)


@customer_bp.route('/product/<slug>/review', methods=['POST'])
@login_required
def add_review(slug):
    product = svc.product_by_slug(slug) or abort(404)
    rating = request.form.get('rating', type=int)
    if rating not in (1, 2, 3, 4, 5):
        flash('Choose a rating from 1 to 5.', 'danger')
        return redirect(url_for('customer.product_detail', slug=slug))
    verified = db.session.query(OrderItem.id).join(Order).filter(
        Order.user_id == current_user.id, OrderItem.product_id == product.id,
        Order.status == 'received').first() is not None
    review = Review.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if review is None:
        review = Review(user_id=current_user.id, product_id=product.id)
        db.session.add(review)
    review.rating, review.body = rating, (request.form.get('body') or '').strip()[:2000]
    review.verified_purchase = verified
    db.session.commit()
    flash('Thanks for your review!', 'success')
    return redirect(url_for('customer.product_detail', slug=slug))


# ------------------------------------------------------------------ wishlist
@customer_bp.route('/wishlist')
@login_required
def wishlist():
    items = (WishlistItem.query.filter_by(user_id=current_user.id).order_by(WishlistItem.id.desc()).all())
    products = [i.product for i in items if svc.product_by_slug(i.product.slug)]
    return render_template('customer/wishlist.html', products=products)


@customer_bp.route('/wishlist/toggle/<int:product_id>', methods=['POST'])
@login_required
def wishlist_toggle(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    item = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if item:
        db.session.delete(item)
        flash('Removed from wishlist.', 'info')
    elif svc.product_by_slug(product.slug):
        db.session.add(WishlistItem(user_id=current_user.id, product_id=product.id))
        flash('Saved to wishlist.', 'success')
    db.session.commit()
    return redirect(request.referrer or url_for('customer.wishlist'))


# ------------------------------------------------------------------ cart
def _resolve_variant(product):
    """Pick the variant from posted option selections (or an explicit variant_id)."""
    vid = request.form.get('variant_id', type=int)
    if vid:
        v = db.session.get(ProductVariant, vid)
        return v if v and v.product_id == product.id and v.is_active else None
    groups = product.options or {}
    combo = []
    for group, values in groups.items():
        choice = request.form.get(f'opt_{group}')
        if choice not in values:
            return None
        combo.append((group, choice))
    key = combo_key(combo) if combo else ''
    return ProductVariant.query.filter_by(product_id=product.id, option_key=key, is_active=True).first()


@customer_bp.route('/cart')
@login_required
def cart():
    lines = pricing.cart_lines(current_user)
    total = pricing.money(sum((l.line_total for l in lines), 0))
    return render_template('customer/cart.html', lines=lines, items=[l.item for l in lines], total=total)


@customer_bp.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if not svc.product_by_slug(product.slug):
        abort(404)
    back = redirect(url_for('customer.product_detail', slug=product.slug))
    variant = _resolve_variant(product)
    if variant is None:
        flash('Please choose all options (e.g. size and colour).', 'warning')
        return back
    qty = request.form.get('quantity', 1, type=int) or 1
    qty = max(1, min(qty, 99))
    item = CartItem.query.filter_by(user_id=current_user.id, variant_id=variant.id).first()
    wanted = qty + (item.quantity if item else 0)
    if variant.available < wanted:
        flash(f'Only {variant.available} available.' if variant.available else 'Out of stock.', 'warning')
        return back
    if item:
        item.quantity = wanted
    else:
        db.session.add(CartItem(user_id=current_user.id, product_id=product.id, variant_id=variant.id, quantity=qty))
    db.session.commit()
    flash('Added to cart.', 'success')
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    item = db.session.get(CartItem, item_id) or abort(404)
    if item.user_id != current_user.id:
        abort(403)
    qty = request.form.get('quantity', type=int)
    if qty and qty > 0:
        avail = item.variant.available if item.variant else 0
        if qty > avail:
            flash(f'Only {avail} available.', 'warning')
            qty = max(1, avail)
        item.quantity = min(qty, 99)
        db.session.commit()
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    item = db.session.get(CartItem, item_id) or abort(404)
    if item.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('customer.cart'))


# ------------------------------------------------------------------ addresses
def _address_from_form(addr):
    name = (request.form.get('recipient_name') or '').strip()
    phone = normalize_phone(request.form.get('phone')) or (request.form.get('phone') or '').strip()
    line = (request.form.get('address_line') or '').strip()
    if not (name and phone and line):
        return 'Recipient name, phone and address are required.'
    addr.label = (request.form.get('label') or '').strip()[:50]
    addr.recipient_name, addr.phone, addr.address_line = name[:100], phone[:20], line
    addr.city = (request.form.get('city') or '').strip()[:80]
    addr.postal_code = (request.form.get('postal_code') or '').strip()[:20]
    return None


def _set_default(addr):
    Address.query.filter(Address.user_id == current_user.id, Address.id != addr.id).update({'is_default': False})
    addr.is_default = True


@customer_bp.route('/account/addresses')
@login_required
def addresses():
    return render_template('customer/addresses.html', addresses=current_user.addresses)


@customer_bp.route('/account/addresses/new', methods=['GET', 'POST'])
@customer_bp.route('/account/addresses/<int:address_id>/edit', methods=['GET', 'POST'])
@login_required
def address_form(address_id=None):
    addr = None
    if address_id:
        addr = db.session.get(Address, address_id) or abort(404)
        if addr.user_id != current_user.id:
            abort(403)
    if request.method == 'POST':
        new = addr is None
        addr = addr or Address(user_id=current_user.id)
        err = _address_from_form(addr)
        if err:
            flash(err, 'danger')
        else:
            if new:
                db.session.add(addr)
                db.session.flush()
            if request.form.get('is_default') or not Address.query.filter(
                    Address.user_id == current_user.id, Address.id != addr.id, Address.is_default.is_(True)).first():
                _set_default(addr)
            db.session.commit()
            flash('Address saved.', 'success')
            return redirect(request.args.get('next') if (request.args.get('next') or '').startswith('/') and
                            not (request.args.get('next') or '').startswith('//') else url_for('customer.addresses'))
    return render_template('customer/address_form.html', address=addr)


@customer_bp.route('/account/addresses/<int:address_id>/delete', methods=['POST'])
@login_required
def address_delete(address_id):
    addr = db.session.get(Address, address_id) or abort(404)
    if addr.user_id != current_user.id:
        abort(403)
    db.session.delete(addr)
    db.session.commit()
    flash('Address removed.', 'info')
    return redirect(url_for('customer.addresses'))


@customer_bp.route('/account/addresses/<int:address_id>/default', methods=['POST'])
@login_required
def address_default(address_id):
    addr = db.session.get(Address, address_id) or abort(404)
    if addr.user_id != current_user.id:
        abort(403)
    _set_default(addr)
    db.session.commit()
    return redirect(url_for('customer.addresses'))


# ------------------------------------------------------------------ checkout
def _checkout_address():
    """Resolve the address from a saved id, new fields, or the legacy single textarea."""
    aid = request.form.get('address_id', type=int)
    if aid:
        a = db.session.get(Address, aid)
        if not a or a.user_id != current_user.id:
            return None, 'Please choose a valid address.'
        return dict(name=a.recipient_name, phone=a.phone, city=a.city, address_line=a.address_line,
                    postal_code=a.postal_code), None
    line = (request.form.get('address_line') or request.form.get('address') or '').strip()
    if not line:
        return None, 'Shipping address is required.'
    data = dict(name=(request.form.get('recipient_name') or current_user.name).strip(),
                phone=normalize_phone(request.form.get('phone')) or current_user.phone,
                city=(request.form.get('city') or '').strip(), address_line=line,
                postal_code=(request.form.get('postal_code') or '').strip())
    if request.form.get('save_address'):
        a = Address(user_id=current_user.id, recipient_name=data['name'], phone=data['phone'], city=data['city'],
                    address_line=line, postal_code=data['postal_code'],
                    is_default=not current_user.addresses)
        db.session.add(a)
        db.session.commit()
    return data, None


@customer_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    lines = pricing.cart_lines(current_user)
    if not lines:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('customer.index'))
    shipping_code = request.values.get('shipping_method')
    coupon_code = (request.values.get('coupon') or '').strip()
    method = request.values.get('payment_method', 'cod')
    q = pricing.quote(current_user, shipping_code, coupon_code)
    if request.method == 'POST' and request.form.get('action') != 'quote':
        address, err = _checkout_address()
        if err:
            flash(err, 'danger')
        else:
            order, err = order_service.create_order(current_user, address, shipping_code, coupon_code, method)
            if err:
                flash(err, 'danger')
                return redirect(url_for('customer.cart') if 'stock' in err.lower() else url_for('customer.checkout'))
            flash(f'Order #{order.id} placed successfully!', 'success')
            if order.payment_method == 'online':
                return redirect(url_for('payment.pay', order_id=order.id), code=307)
            return redirect(url_for('customer.order_detail', order_id=order.id))
    return render_template('customer/checkout.html', items=[l.item for l in lines], quote=q,
                           methods=pricing.shipping_methods(), payment_methods=order_service.available_payment_methods(),
                           selected_method=method, coupon_code=coupon_code, selected_shipping=q.method.code if q.method else None,
                           addresses=current_user.addresses)


# ------------------------------------------------------------------ orders
@customer_bp.route('/orders')
@login_required
def orders():
    page = request.args.get('page', 1, type=int)
    pg = (Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc(), Order.id.desc())
          .paginate(page=page, per_page=10, error_out=False))
    return render_template('customer/orders.html', orders=pg.items, page=pg)


@customer_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    if order.user_id != current_user.id and not current_user.is_staff():
        abort(403)
    return render_template('customer/order_detail.html', order=order)


@customer_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def order_cancel(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    try:
        order_service.customer_cancel(order, current_user)
        flash('Order cancelled.', 'info')
    except order_service.InvalidTransition as e:
        flash(str(e), 'warning')
    return redirect(url_for('customer.order_detail', order_id=order_id))


@customer_bp.route('/orders/<int:order_id>/received', methods=['POST'])
@login_required
def order_received(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    try:
        order_service.customer_confirm_received(order, current_user)
        flash('Thanks for confirming delivery.', 'success')
    except order_service.InvalidTransition as e:
        flash(str(e), 'warning')
    return redirect(url_for('customer.order_detail', order_id=order_id))


# ------------------------------------------------------------------ SEO
@customer_bp.route('/robots.txt')
def robots():
    base = (current_app.config.get('SITE_URL') or request.url_root).rstrip('/')
    body = ('User-agent: *\nDisallow: /staff/\nDisallow: /admin/\nDisallow: /admin-panel/\nDisallow: /cart\n'
            'Disallow: /checkout\nDisallow: /orders\nDisallow: /auth/\n'
            f'Sitemap: {base}/sitemap.xml\n')
    resp = make_response(body)
    resp.mimetype = 'text/plain'
    return resp


@customer_bp.route('/sitemap.xml')
def sitemap():
    base = (current_app.config.get('SITE_URL') or request.url_root).rstrip('/')
    urls = [(f'{base}/', None), (f'{base}/shop', None)]
    for c in Category.query.filter(Category.public_effective.is_(True)).order_by(Category.id).all():
        urls.append((f"{base}{url_for('customer.category', slug=c.slug)}", None))
    for p in (Product.query.filter(svc.public_product_clause()).order_by(Product.id).limit(50000).all()):
        urls.append((f"{base}{url_for('customer.product_detail', slug=p.slug)}", p.updated_at))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, mod in urls:
        xml.append(f'<url><loc>{loc}</loc>' + (f'<lastmod>{mod.strftime("%Y-%m-%d")}</lastmod>' if mod else '') + '</url>')
    xml.append('</urlset>')
    resp = make_response('\n'.join(xml))
    resp.mimetype = 'application/xml'
    return resp
