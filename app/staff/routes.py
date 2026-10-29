import logging
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, flash, request, send_file, abort, current_app)
from flask_login import login_required, current_user
from werkzeug.datastructures import MultiDict
from sqlalchemy import func, or_

from ..models import (Product, Category, Order, OrderItem, Tag, product_tags, ORDER_STATUSES, PAYMENT_STATUSES,
                      PRODUCT_STATUSES, HomepageSection, Banner)
from ..extensions import db
from ..i18n import flash  # translated flash messages
from ..decorators import staff_required, permission_required
from ..utils import slugify, unique_slug, escape_like
from ..uploads import save_image, validate_image_url, UploadError
from ..services import catalog as svc, orders as order_service, importer
from ..services.products import save_product, options_to_text, delete_or_archive

staff_bp = Blueprint('staff', __name__)
log = logging.getLogger(__name__)
PER_PAGE = 20


def staff_view(perm):
    """login + permission guard used by every staff route."""
    def deco(f):
        return login_required(permission_required(perm)(f))
    return deco


# ------------------------------------------------------------------ dashboard
@staff_bp.route('/')
@login_required
@staff_required
def dashboard():
    revenue = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
        Order.status.notin_(('cancelled', 'failed'))).scalar()
    return render_template(
        'panel/dashboard.html', total_products=Product.query.count(), total_orders=Order.query.count(),
        pending_orders=Order.query.filter_by(status='pending').count(), revenue=revenue,
        recent_orders=Order.query.order_by(Order.created_at.desc()).limit(5).all())


# ------------------------------------------------------------------ products
@staff_bp.route('/products')
@staff_view('catalog')
def products():
    q = Product.query
    term = (request.args.get('q') or '').strip()
    status = request.args.get('status')
    cat_id = request.args.get('category', type=int)
    if term:
        like = f'%{escape_like(term)}%'
        q = q.filter(or_(Product.name.ilike(like, escape='\\'), Product.sku.ilike(like, escape='\\'),
                         Product.brand.ilike(like, escape='\\')))
    if status in PRODUCT_STATUSES:
        q = q.filter(Product.status == status)
    if cat_id:
        cat = db.session.get(Category, cat_id)
        if cat:
            q = q.filter(svc._category_clause(cat, public_only=False))
    sort = request.args.get('sort', 'newest')
    order = {'newest': (Product.created_at.desc(), Product.id.desc()), 'name': (Product.name.asc(),),
             'price_asc': (Product.min_price.asc(),), 'price_desc': (Product.min_price.desc(),)}.get(
        sort, (Product.created_at.desc(),))
    pg = q.order_by(*order).paginate(page=request.args.get('page', 1, type=int), per_page=PER_PAGE, error_out=False)
    return render_template('panel/products.html', products=pg.items, page=pg, term=term, status=status, sort=sort,
                           cat_id=cat_id, categories=svc.flat_tree(),
                           args={k: v for k, v in request.args.items() if k != 'page'})


def _attr_lines(product):
    if not product:
        return []
    grouped = {}
    for pav in product.attribute_values:
        grouped.setdefault(pav.attribute.name, []).append(pav.value)
    return [f'{k}: {", ".join(v)}' for k, v in grouped.items()]


def _product_form(product):
    if request.method == 'POST':
        saved, errors = save_product(product, request.form, request.files, current_user)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, 'danger')
        else:
            db.session.commit()
            flash('Product saved.', 'success')
            return redirect(url_for('staff.product_edit', product_id=saved.id))
    return render_template('panel/product_form.html', product=product, categories=svc.flat_tree(),
                           tags=Tag.query.order_by(Tag.name).all(), form_data=request.form if request.method == 'POST' else MultiDict(),
                           options_text=options_to_text(product.options) if product else '',
                           product_attr_lines=_attr_lines(product))


@staff_bp.route('/products/new', methods=['GET', 'POST'])
@staff_view('catalog')
def product_new():
    return _product_form(None)


@staff_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@staff_view('catalog')
def product_edit(product_id):
    return _product_form(db.session.get(Product, product_id) or abort(404))


@staff_bp.route('/products/<int:product_id>/status', methods=['POST'])
@staff_view('catalog')
def product_status(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    new = request.form.get('status')
    if new in PRODUCT_STATUSES:
        product.status = new
        db.session.commit()
        flash(f'Product is now {new}.', 'success')
    return redirect(request.referrer or url_for('staff.products'))


@staff_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@staff_view('catalog')
def product_delete(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    result = delete_or_archive(product)
    flash('Product deleted.' if result == 'deleted' else
          'Product has order history, so it was archived instead of deleted.', 'info')
    return redirect(url_for('staff.products'))


# ------------------------------------------------------------------ categories (infinite tree)
@staff_bp.route('/categories')
@staff_view('catalog')
def categories():
    counts = dict(db.session.query(Category.id, func.count(Product.id)).outerjoin(
        Product, Product.category_id == Category.id).group_by(Category.id).all())
    return render_template('panel/categories.html', tree=svc.flat_tree(public_only=False), counts=counts)


def _category_form(category):
    parent_id = request.form.get('parent_id', type=int) if request.method == 'POST' else (category.parent_id if category else request.args.get('parent', type=int))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        err = None
        parent, perr = svc.validate_parent(category, parent_id)
        if not name:
            err = 'Name is required.'
        elif perr:
            err = perr
        else:
            dup = Category.query.filter(func.lower(Category.name) == name.lower(),
                                        Category.parent_id == (parent.id if parent else None))
            if category:
                dup = dup.filter(Category.id != category.id)
            if dup.first():
                err = 'A category with this name already exists at this level.'
        image = (request.form.get('image_url') or '').strip()
        try:
            f = request.files.get('image')
            if f and f.filename:
                image = save_image(f, 'categories')
            elif image:
                image = validate_image_url(image)
        except UploadError as e:
            err = str(e)
        if err:
            flash(err, 'danger')
        else:
            new = category is None
            category = category or Category(name=name, slug='tmp')
            category.name = name
            slug_in = slugify(request.form.get('slug') or '') or name
            category.slug = unique_slug(Category, slug_in, exclude_id=None if new else category.id)
            category.parent = parent
            category.visible = request.form.get('visible') == 'on'
            category.is_internal = request.form.get('is_internal') == 'on'
            category.description = (request.form.get('description') or '').strip()
            category.sort_order = request.form.get('sort_order', 0, type=int) or 0
            category.image_url = image
            if new:
                db.session.add(category)
            db.session.flush()
            svc.rebuild_subtree(category)
            db.session.commit()
            flash('Category saved.', 'success')
            return redirect(url_for('staff.categories'))
    exclude = category.path if category and category.path else None
    parents = [(c, d) for c, d in svc.flat_tree(public_only=False)
               if not (exclude and (c.path or '').startswith(exclude))]
    return render_template('panel/category_form.html', category=category, parents=parents, parent_id=parent_id,
                           form_data=request.form if request.method == 'POST' else {})


@staff_bp.route('/categories/new', methods=['GET', 'POST'])
@staff_view('catalog')
def category_new():
    return _category_form(None)


@staff_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@staff_view('catalog')
def category_edit(category_id):
    return _category_form(db.session.get(Category, category_id) or abort(404))


@staff_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@staff_view('catalog')
def category_delete(category_id):
    category = db.session.get(Category, category_id) or abort(404)
    in_use = db.session.query(func.count()).select_from(
        svc.product_categories).where(svc.product_categories.c.category_id == category.id).scalar()
    if category.children:
        flash('Move or delete the sub-categories first.', 'danger')
    elif category.products or in_use:
        flash('Cannot delete a category that has products.', 'danger')
    elif HomepageSection.query.filter_by(source_category_id=category.id).first() or Banner.query.filter_by(category_id=category.id).first():
        flash('This category is used by a homepage section or banner.', 'danger')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('Category deleted.', 'info')
    return redirect(url_for('staff.categories'))


# ------------------------------------------------------------------ tags
@staff_bp.route('/tags', methods=['GET', 'POST'])
@staff_view('catalog')
def tags():
    if request.method == 'POST':
        created = [svc.get_or_create_tag(n) for n in request.form.get('names', '').replace('\n', ',').split(',') if n.strip()]
        db.session.commit()
        flash(f'{len([t for t in created if t])} tag(s) saved.', 'success')
        return redirect(url_for('staff.tags'))
    rows = (db.session.query(Tag, func.count(product_tags.c.product_id)).outerjoin(
        product_tags, product_tags.c.tag_id == Tag.id).group_by(Tag.id).order_by(Tag.name).all())
    return render_template('panel/tags.html', rows=rows)


@staff_bp.route('/tags/<int:tag_id>/rename', methods=['POST'])
@staff_view('catalog')
def tag_rename(tag_id):
    tag = db.session.get(Tag, tag_id) or abort(404)
    name = (request.form.get('name') or '').strip()[:50]
    slug = slugify(name)
    if not slug:
        flash('Tag name is required.', 'danger')
    elif Tag.query.filter(Tag.slug == slug, Tag.id != tag.id).first():
        flash('Another tag already has that name.', 'danger')
    else:
        tag.name, tag.slug = name, slug[:60]
        db.session.commit()
        flash('Tag renamed.', 'success')
    return redirect(url_for('staff.tags'))


@staff_bp.route('/tags/<int:tag_id>/delete', methods=['POST'])
@staff_view('catalog')
def tag_delete(tag_id):
    tag = db.session.get(Tag, tag_id) or abort(404)
    tag.products = []
    db.session.delete(tag)
    db.session.commit()
    flash('Tag deleted.', 'info')
    return redirect(url_for('staff.tags'))


# ------------------------------------------------------------------ bulk import / export
@staff_bp.route('/import', methods=['GET', 'POST'])
@staff_view('catalog')
def import_products():
    report = None
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename:
            flash('Choose a .xlsx or .csv file.', 'danger')
        else:
            try:
                report = importer.import_file(f.stream, f.filename, apply=request.form.get('mode') == 'apply')
                if report.dry_run:
                    flash('Dry run finished - nothing was saved.', 'info')
                elif report.ok:
                    flash(f'Import complete: {report.created} created, {report.updated} updated.', 'success')
                else:
                    flash('Import finished with some errors (valid rows were saved).', 'warning')
            except importer.ImportError_ as e:
                flash(str(e), 'danger')
            except Exception:
                db.session.rollback()
                log.exception('Product import failed')
                flash('The file could not be processed.', 'danger')
    return render_template('panel/import.html', report=report)


@staff_bp.route('/import/template.xlsx')
@staff_view('catalog')
def import_template():
    return send_file(importer.build_template(), as_attachment=True, download_name='products-template.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@staff_bp.route('/export/products.xlsx')
@staff_view('catalog')
def export_products():
    return send_file(importer.export_products(), as_attachment=True, download_name='products.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ------------------------------------------------------------------ orders
@staff_bp.route('/orders')
@staff_view('orders')
def orders():
    status = request.args.get('status')
    q = Order.query
    if status in ORDER_STATUSES:
        q = q.filter_by(status=status)
    pay = request.args.get('payment')
    if pay in PAYMENT_STATUSES:
        q = q.filter_by(payment_status=pay)
    term = (request.args.get('q') or '').strip()
    if term.isdigit():
        q = q.filter(Order.id == int(term))
    elif term:
        q = q.filter(or_(Order.ship_phone.like(f'%{escape_like(term)}%', escape='\\'),
                         Order.tracking_code == term))
    pg = q.order_by(Order.created_at.desc(), Order.id.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=PER_PAGE, error_out=False)
    return render_template('panel/orders.html', orders=pg.items, page=pg, current_status=status, statuses=ORDER_STATUSES,
                           term=term, args={k: v for k, v in request.args.items() if k != 'page'})


@staff_bp.route('/orders/<int:order_id>', methods=['GET', 'POST'])
@staff_view('orders')
def order_detail(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    if request.method == 'POST':
        action = request.form.get('action', 'transition')
        try:
            if action == 'refund':
                if not current_user.is_admin():
                    abort(403)
                order_service.mark_refunded(order, current_user)
                flash('Marked as refunded.', 'success')
            else:
                order_service.transition_order(
                    order, request.form.get('status'), current_user, (request.form.get('note') or '').strip(),
                    provider=request.form.get('provider'), tracking=request.form.get('tracking'))
                flash('Order status updated.', 'success')
        except order_service.InvalidTransition as e:
            flash(str(e), 'danger')
        return redirect(url_for('staff.order_detail', order_id=order.id))
    return render_template('panel/order_detail.html', order=order)


from . import settings  # noqa: E402,F401  (registers settings/homepage/banner/coupon/shipping routes)
