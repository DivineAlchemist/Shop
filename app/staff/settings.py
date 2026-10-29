"""Store settings, homepage sections, banners, coupons and shipping methods (staff panel)."""
from datetime import datetime
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request, abort

from .routes import staff_bp, staff_view
from ..extensions import db
from ..i18n import flash  # translated flash messages
from ..models import (StoreSettings, HomepageSection, Banner, Coupon, ShippingMethod, Product, Category,
                      BANNER_LINK_TYPES)
from ..services import catalog as svc
from ..uploads import save_image, validate_image_url, UploadError
from ..utils import to_decimal

CURRENCIES = ['USD', 'EUR', 'GBP', 'IRT', 'IRR']
from ..i18n import LANGUAGES
LOCALES = [(k, v['name']) for k, v in LANGUAGES.items()]


def _f(name, label, type='text', value='', **kw):
    return dict(name=name, label=label, type=type, value=value, **kw)


def _val(form_data, obj, name, default=''):
    if form_data and name in form_data:
        return form_data.get(name)
    v = getattr(obj, name, default) if obj is not None else default
    return '' if v is None else v


def _image_field(field_name, subdir, current, allow_ico=False):
    f = request.files.get(f'{field_name}_file')
    typed = (request.form.get(field_name) or '').strip()
    if f and f.filename:
        return save_image(f, subdir, allow_ico=allow_ico)
    return validate_image_url(typed) if typed else ''


def render_form(title, fields, cancel, note=None):
    return render_template('panel/generic_form.html', title=title, fields=fields, cancel_url=cancel, note=note)


def category_options(blank='— None —'):
    opts = [('', blank)]
    for c, depth in svc.flat_tree(public_only=False):
        flag = ' (internal)' if c.is_internal else (' (hidden)' if not c.visible else '')
        opts.append((str(c.id), '\u2003' * depth + c.name + flag))
    return opts


# ------------------------------------------------------------------ store settings
@staff_bp.route('/settings', methods=['GET', 'POST'])
@staff_view('settings')
def store_settings():
    s = StoreSettings.query.first()
    if s is None:
        s = StoreSettings()
        db.session.add(s)
        db.session.flush()
    fd = request.form if request.method == 'POST' else {}
    social = s.social_links or {}
    if request.method == 'POST':
        try:
            if not (request.form.get('store_name') or '').strip():
                raise UploadError('Store name is required.')
            if request.form.get('currency') not in CURRENCIES or request.form.get('locale') not in dict(LOCALES):
                raise UploadError('Invalid currency or locale.')
            s.logo_url = _image_field('logo_url', 'store', s.logo_url)
            s.favicon_url = _image_field('favicon_url', 'store', s.favicon_url, allow_ico=True)
            s.banner_image_url = _image_field('banner_image_url', 'store', s.banner_image_url)
            s.og_image_url = _image_field('og_image_url', 'store', s.og_image_url)
            for col in ('store_name', 'description', 'domain', 'contact_email', 'contact_phone', 'address',
                        'banner_title', 'banner_link', 'currency', 'locale', 'shipping_info', 'return_policy',
                        'seo_title', 'seo_description', 'seo_keywords'):
                setattr(s, col, (request.form.get(col) or '').strip())
            s.social_links = {k: (request.form.get(f'social_{k}') or '').strip()
                              for k in ('instagram', 'telegram', 'whatsapp', 'twitter', 'youtube')
                              if (request.form.get(f'social_{k}') or '').strip()}
            db.session.commit()
            flash('Settings saved.', 'success')
            return redirect(url_for('staff.store_settings'))
        except UploadError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            s = StoreSettings.query.first() or s
    v = lambda n: _val(fd, s, n)
    fields = [
        _f('store_name', 'Store name', value=v('store_name'), required=True, cols=6),
        _f('domain', 'Domain', value=v('domain'), cols=6),
        _f('description', 'Description', 'textarea', v('description')),
        _f('logo_url', 'Logo (URL or upload)', 'image', v('logo_url'), cols=6),
        _f('favicon_url', 'Favicon (png/ico)', 'image', v('favicon_url'), cols=6),
        _f('contact_email', 'Contact email', value=v('contact_email'), cols=6),
        _f('contact_phone', 'Contact phone', value=v('contact_phone'), cols=6),
        _f('address', 'Physical address', 'textarea', v('address')),
        _f('banner_title', 'Fallback banner title', value=v('banner_title'), cols=6),
        _f('banner_link', 'Fallback banner link', value=v('banner_link'), cols=6),
        _f('banner_image_url', 'Fallback banner image (used when no slider banners exist)', 'image', v('banner_image_url')),
        _f('currency', 'Currency', 'select', v('currency'), options=[(c, c) for c in CURRENCIES], cols=6,
           help='Online payment (Zarinpal) needs IRT (Toman) or IRR (Rial).'),
        _f('locale', 'Website language', 'select', v('locale'), options=LOCALES, cols=6,
           help='Changes the language of the whole site and its direction (English: left-to-right, فارسی: right-to-left). SMS messages use it too.'),
        _f('shipping_info', 'Shipping information', 'textarea', v('shipping_info')),
        _f('return_policy', 'Return policy', 'textarea', v('return_policy')),
        _f('seo_title', 'SEO title', value=v('seo_title'), cols=6),
        _f('seo_keywords', 'SEO keywords', value=v('seo_keywords'), cols=6),
        _f('seo_description', 'SEO description', 'textarea', v('seo_description')),
        _f('og_image_url', 'Social share image', 'image', v('og_image_url')),
    ] + [_f(f'social_{k}', k.capitalize() + ' URL', value=fd.get(f'social_{k}', social.get(k, '')) if fd else social.get(k, ''), cols=6)
         for k in ('instagram', 'telegram', 'whatsapp', 'twitter', 'youtube')]
    return render_form('Store settings', fields, url_for('staff.dashboard'),
                       note='API keys and merchant IDs are configured through environment variables, never here.')


# ------------------------------------------------------------------ homepage sections
@staff_bp.route('/homepage')
@staff_view('settings')
def sections():
    rows = []
    for s in HomepageSection.query.order_by(HomepageSection.position, HomepageSection.id).all():
        src = s.source_category
        rows.append(dict(cells=[s.display_title, (src.name + (' (internal)' if src.is_internal else '')) if src else 'All products',
                                s.product_limit, 'on (%ss)' % s.scroll_interval if s.auto_scroll else 'off',
                                'yes' if (s.is_active and s.visible) else 'no'],
                         actions=[('Edit', url_for('staff.section_edit', section_id=s.id), None, None),
                                  ('Delete', url_for('staff.section_delete', section_id=s.id), 'post', 'Delete this section?')]))
    return render_template('panel/generic_list.html', title='Homepage sections',
                           actions=[('New section', url_for('staff.section_new'))],
                           columns=['Title', 'Source category', 'Products', 'Auto-scroll', 'Shown'], rows=rows,
                           empty='No sections yet.')


def _section_form(section):
    fd = request.form if request.method == 'POST' else {}
    if request.method == 'POST':
        cat_id = request.form.get('source_category_id', type=int)
        limit = request.form.get('product_limit', 10, type=int) or 10
        interval = request.form.get('scroll_interval', 5, type=int) or 5
        if cat_id and not db.session.get(Category, cat_id):
            flash('Unknown category.', 'danger')
        elif not (request.form.get('title') or '').strip() and not cat_id:
            flash('Enter a title or choose a category.', 'danger')
        else:
            new = section is None
            section = section or HomepageSection()
            section.title = (request.form.get('title') or '').strip()
            section.description = (request.form.get('description') or '').strip()[:300]
            section.source_category_id = cat_id
            section.include_subcategories = request.form.get('include_subcategories') == 'on'
            section.product_limit = max(1, min(limit, 50))
            section.auto_scroll = request.form.get('auto_scroll') == 'on'
            section.scroll_interval = max(2, min(interval, 60))
            section.position = request.form.get('position', 0, type=int) or 0
            section.is_active = request.form.get('is_active') == 'on'
            section.visible = request.form.get('visible') == 'on'
            if new:
                db.session.add(section)
            db.session.commit()
            flash('Section saved.', 'success')
            return redirect(url_for('staff.sections'))
    s = section
    def v(n, d=''):
        return _val(fd, s, n, d)
    chk = lambda n, d=True: (fd.get(n) == 'on') if fd else (getattr(s, n) if s else d)
    fields = [
        _f('source_category_id', 'Source category (normal or internal)', 'select', str(v('source_category_id')),
           options=category_options('All public products'),
           help='Shows the 10 latest published products of this category. Internal categories are allowed here; products must still be publicly visible.'),
        _f('title', 'Title (leave empty to use the category name)', value=v('title'), cols=8),
        _f('product_limit', 'Number of products', 'number', v('product_limit', 10), cols=4, min=1, max=50),
        _f('description', 'Description (optional)', value=v('description')),
        _f('include_subcategories', 'Include products of sub-categories', 'checkbox', chk('include_subcategories'), cols=6),
        _f('auto_scroll', 'Auto-scroll the product card', 'checkbox', chk('auto_scroll', False), cols=6),
        _f('scroll_interval', 'Auto-scroll interval (seconds)', 'number', v('scroll_interval', 5), cols=4, min=2, max=60),
        _f('position', 'Order on page', 'number', v('position', 0), cols=4),
        _f('is_active', 'Active', 'checkbox', chk('is_active'), cols=2),
        _f('visible', 'Visible', 'checkbox', chk('visible'), cols=2),
    ]
    return render_form('Edit section' if section else 'New section', fields, url_for('staff.sections'))


@staff_bp.route('/homepage/new', methods=['GET', 'POST'])
@staff_view('settings')
def section_new():
    return _section_form(None)


@staff_bp.route('/homepage/<int:section_id>/edit', methods=['GET', 'POST'])
@staff_view('settings')
def section_edit(section_id):
    return _section_form(db.session.get(HomepageSection, section_id) or abort(404))


@staff_bp.route('/homepage/<int:section_id>/delete', methods=['POST'])
@staff_view('settings')
def section_delete(section_id):
    db.session.delete(db.session.get(HomepageSection, section_id) or abort(404))
    db.session.commit()
    flash('Section deleted.', 'info')
    return redirect(url_for('staff.sections'))


# ------------------------------------------------------------------ banners (slider)
@staff_bp.route('/banners')
@staff_view('settings')
def banners():
    rows = []
    for b in Banner.query.order_by(Banner.position, Banner.id).all():
        target = {'product': b.product.name if b.product else '—', 'category': b.category.name if b.category else '—',
                  'url': b.url, 'none': 'No link'}[b.link_type]
        rows.append(dict(cells=[b.title or '(no title)', f'{b.link_type}: {target}', b.position, 'yes' if b.is_active else 'no'],
                         image=b.image_url,
                         actions=[('Edit', url_for('staff.banner_edit', banner_id=b.id), None, None),
                                  ('Delete', url_for('staff.banner_delete', banner_id=b.id), 'post', 'Delete this banner?')]))
    return render_template('panel/generic_list.html', title='Homepage slider banners',
                           actions=[('New banner', url_for('staff.banner_new'))],
                           columns=['Title', 'Links to', 'Position', 'Active'], rows=rows, empty='No banners yet.')


def _find_product(ref):
    ref = (ref or '').strip()
    if not ref:
        return None
    q = Product.query
    if ref.isdigit():
        p = q.filter_by(id=int(ref)).first()
        if p:
            return p
    return q.filter((Product.sku == ref) | (Product.slug == ref)).first()


def _banner_form(banner):
    fd = request.form if request.method == 'POST' else {}
    if request.method == 'POST':
        err = None
        try:
            image = _image_field('image_url', 'banners', banner.image_url if banner else '') or (banner.image_url if banner else '')
        except UploadError as e:
            image, err = '', str(e)
        link = request.form.get('link_type', 'none')
        product = _find_product(request.form.get('product_ref')) if link == 'product' else None
        category = db.session.get(Category, request.form.get('category_id', type=int) or 0) if link == 'category' else None
        url = (request.form.get('url') or '').strip()
        if not err and not image:
            err = 'A banner image is required.'
        elif link not in BANNER_LINK_TYPES:
            err = 'Invalid link type.'
        elif link == 'product' and product is None:
            err = 'Product not found (enter its SKU, slug or id).'
        elif link == 'category' and (category is None or not category.public_effective):
            err = 'Choose a publicly visible category.'
        elif link == 'url' and not (url.startswith('/') and not url.startswith('//') or url.startswith(('http://', 'https://'))):
            err = 'Enter a valid URL.'
        if err:
            flash(err, 'danger')
        else:
            new = banner is None
            banner = banner or Banner()
            banner.title = (request.form.get('title') or '').strip()[:150]
            banner.subtitle = (request.form.get('subtitle') or '').strip()[:300]
            banner.button_text = (request.form.get('button_text') or '').strip()[:40]
            banner.image_url = image
            banner.link_type = link
            banner.product_id = product.id if product else None
            banner.category_id = category.id if category else None
            banner.url = url if link == 'url' else ''
            banner.position = request.form.get('position', 0, type=int) or 0
            banner.autoplay_seconds = max(2, min(request.form.get('autoplay_seconds', 5, type=int) or 5, 60))
            banner.is_active = request.form.get('is_active') == 'on'
            if new:
                db.session.add(banner)
            db.session.commit()
            flash('Banner saved.', 'success')
            return redirect(url_for('staff.banners'))
    b = banner
    v = lambda n, d='': _val(fd, b, n, d)
    prod_ref = fd.get('product_ref') if fd else ((b.product.sku or b.product.slug) if b and b.product else '')
    fields = [
        _f('image_url', 'Image (upload or URL)', 'image', v('image_url'), help='Wide images (e.g. 1600×600) look best.'),
        _f('title', 'Title', value=v('title'), cols=6),
        _f('button_text', 'Button text', value=v('button_text'), cols=6),
        _f('subtitle', 'Subtitle', value=v('subtitle')),
        _f('link_type', 'Links to', 'select', v('link_type', 'none'), cols=4,
           options=[('none', 'Nothing'), ('product', 'A product'), ('category', 'A category'), ('url', 'Custom URL')]),
        _f('product_ref', 'Product (SKU, slug or id)', value=prod_ref, cols=4),
        _f('category_id', 'Category', 'select', str(v('category_id')), options=category_options(), cols=4),
        _f('url', 'Custom URL', value=v('url')),
        _f('position', 'Position', 'number', v('position', 0), cols=4),
        _f('autoplay_seconds', 'Seconds on screen', 'number', v('autoplay_seconds', 5), cols=4),
        _f('is_active', 'Active', 'checkbox', (fd.get('is_active') == 'on') if fd else (b.is_active if b else True), cols=4),
    ]
    return render_form('Edit banner' if banner else 'New banner', fields, url_for('staff.banners'))


@staff_bp.route('/banners/new', methods=['GET', 'POST'])
@staff_view('settings')
def banner_new():
    return _banner_form(None)


@staff_bp.route('/banners/<int:banner_id>/edit', methods=['GET', 'POST'])
@staff_view('settings')
def banner_edit(banner_id):
    return _banner_form(db.session.get(Banner, banner_id) or abort(404))


@staff_bp.route('/banners/<int:banner_id>/delete', methods=['POST'])
@staff_view('settings')
def banner_delete(banner_id):
    db.session.delete(db.session.get(Banner, banner_id) or abort(404))
    db.session.commit()
    flash('Banner deleted.', 'info')
    return redirect(url_for('staff.banners'))


# ------------------------------------------------------------------ coupons
@staff_bp.route('/coupons')
@staff_view('coupons')
def coupons():
    rows = [dict(cells=[c.code, f'{c.value}{"%" if c.kind == "percent" else ""}', c.min_subtotal,
                        f'{c.used_count}/{c.usage_limit or "∞"}', 'yes' if c.is_active else 'no'],
                 actions=[('Edit', url_for('staff.coupon_edit', coupon_id=c.id), None, None)])
            for c in Coupon.query.order_by(Coupon.id.desc()).all()]
    return render_template('panel/generic_list.html', title='Coupons', actions=[('New coupon', url_for('staff.coupon_new'))],
                           columns=['Code', 'Discount', 'Min. subtotal', 'Used', 'Active'], rows=rows, empty='No coupons.')


def _dt(raw):
    try:
        return datetime.strptime(raw, '%Y-%m-%dT%H:%M') if raw else None
    except ValueError:
        raise ValueError('Invalid date.')


def _coupon_form(coupon):
    fd = request.form if request.method == 'POST' else {}
    if request.method == 'POST':
        try:
            code = (request.form.get('code') or '').strip().upper()[:40]
            kind = request.form.get('kind')
            value = to_decimal(request.form.get('value'))
            if not code or kind not in ('percent', 'fixed') or value is None or value <= 0 or (kind == 'percent' and value > 100):
                raise ValueError('Code, a valid type and a positive value (max 100 for percent) are required.')
            if Coupon.query.filter(db.func.upper(Coupon.code) == code, Coupon.id != (coupon.id if coupon else 0)).first():
                raise ValueError('That code already exists.')
            new = coupon is None
            coupon = coupon or Coupon()
            coupon.code, coupon.kind, coupon.value = code, kind, value
            coupon.min_subtotal = to_decimal(request.form.get('min_subtotal'), Decimal('0'))
            coupon.max_discount = to_decimal(request.form.get('max_discount'))
            coupon.usage_limit = request.form.get('usage_limit', type=int)
            coupon.per_user_limit = request.form.get('per_user_limit', type=int)
            coupon.starts_at, coupon.expires_at = _dt(request.form.get('starts_at')), _dt(request.form.get('expires_at'))
            coupon.is_active = request.form.get('is_active') == 'on'
            if new:
                db.session.add(coupon)
            db.session.commit()
            flash('Coupon saved.', 'success')
            return redirect(url_for('staff.coupons'))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
    c = coupon
    v = lambda n, d='': _val(fd, c, n, d)
    dt = lambda n: (fd.get(n) if fd else (getattr(c, n).strftime('%Y-%m-%dT%H:%M') if c and getattr(c, n) else ''))
    fields = [
        _f('code', 'Code', value=v('code'), cols=4), _f('kind', 'Type', 'select', v('kind', 'percent'), cols=4,
                                                          options=[('percent', 'Percent'), ('fixed', 'Fixed amount')]),
        _f('value', 'Value', 'number', v('value'), cols=4, step='0.01'),
        _f('min_subtotal', 'Minimum subtotal', 'number', v('min_subtotal', 0), cols=4, step='0.01'),
        _f('max_discount', 'Maximum discount', 'number', v('max_discount'), cols=4, step='0.01'),
        _f('usage_limit', 'Total usage limit', 'number', v('usage_limit'), cols=4),
        _f('per_user_limit', 'Per-customer limit', 'number', v('per_user_limit'), cols=4),
        _f('starts_at', 'Starts', 'datetime-local', dt('starts_at'), cols=4),
        _f('expires_at', 'Expires', 'datetime-local', dt('expires_at'), cols=4),
        _f('is_active', 'Active', 'checkbox', (fd.get('is_active') == 'on') if fd else (c.is_active if c else True)),
    ]
    return render_form('Edit coupon' if coupon else 'New coupon', fields, url_for('staff.coupons'))


@staff_bp.route('/coupons/new', methods=['GET', 'POST'])
@staff_view('coupons')
def coupon_new():
    return _coupon_form(None)


@staff_bp.route('/coupons/<int:coupon_id>/edit', methods=['GET', 'POST'])
@staff_view('coupons')
def coupon_edit(coupon_id):
    return _coupon_form(db.session.get(Coupon, coupon_id) or abort(404))


# ------------------------------------------------------------------ shipping methods
@staff_bp.route('/shipping')
@staff_view('settings')
def shipping():
    rows = [dict(cells=[m.name, m.code, m.price, m.free_over or '—', 'yes' if m.is_active else 'no'],
                 actions=[('Edit', url_for('staff.shipping_edit', method_id=m.id), None, None)])
            for m in ShippingMethod.query.order_by(ShippingMethod.position, ShippingMethod.id).all()]
    return render_template('panel/generic_list.html', title='Shipping methods',
                           actions=[('New method', url_for('staff.shipping_new'))],
                           columns=['Name', 'Code', 'Price', 'Free over', 'Active'], rows=rows, empty='No shipping methods.')


def _shipping_form(method):
    fd = request.form if request.method == 'POST' else {}
    if request.method == 'POST':
        name, code = (request.form.get('name') or '').strip(), (request.form.get('code') or '').strip().lower()
        price = to_decimal(request.form.get('price'), Decimal('0'))
        if not name or not code or price < 0:
            flash('Name, code and a non-negative price are required.', 'danger')
        elif ShippingMethod.query.filter(ShippingMethod.code == code, ShippingMethod.id != (method.id if method else 0)).first():
            flash('That code already exists.', 'danger')
        else:
            new = method is None
            method = method or ShippingMethod()
            method.name, method.code, method.price = name[:80], code[:30], price
            method.description = (request.form.get('description') or '').strip()[:200]
            method.free_over = to_decimal(request.form.get('free_over'))
            method.position = request.form.get('position', 0, type=int) or 0
            method.is_active = request.form.get('is_active') == 'on'
            if new:
                db.session.add(method)
            db.session.commit()
            flash('Shipping method saved.', 'success')
            return redirect(url_for('staff.shipping'))
    m = method
    v = lambda n, d='': _val(fd, m, n, d)
    fields = [_f('name', 'Name', value=v('name'), cols=6), _f('code', 'Code', value=v('code'), cols=6),
              _f('price', 'Price', 'number', v('price', 0), cols=4, step='0.01'),
              _f('free_over', 'Free when subtotal ≥', 'number', v('free_over'), cols=4, step='0.01'),
              _f('position', 'Position', 'number', v('position', 0), cols=4),
              _f('description', 'Description', value=v('description')),
              _f('is_active', 'Active', 'checkbox', (fd.get('is_active') == 'on') if fd else (m.is_active if m else True))]
    return render_form('Edit shipping method' if method else 'New shipping method', fields, url_for('staff.shipping'))


@staff_bp.route('/shipping/new', methods=['GET', 'POST'])
@staff_view('settings')
def shipping_new():
    return _shipping_form(None)


@staff_bp.route('/shipping/<int:method_id>/edit', methods=['GET', 'POST'])
@staff_view('settings')
def shipping_edit(method_id):
    return _shipping_form(db.session.get(ShippingMethod, method_id) or abort(404))
