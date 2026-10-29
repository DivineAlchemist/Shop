"""Staff-side product persistence: validation, options -> variants, images, tags, attributes."""
import itertools
from decimal import Decimal
from sqlalchemy import func

from ..extensions import db
from ..models import (Product, ProductVariant, VariantOption, ProductImage, Category, CartItem, OrderItem,
                      ProductAttributeValue, PRODUCT_STATUSES)
from ..uploads import save_image, validate_image_url, UploadError
from ..utils import slugify, unique_slug, to_decimal
from .catalog import get_or_create_tag, get_or_create_attribute


# ------------------------------------------------------------------ options
def parse_options(text, existing=None):
    """'Color: Blue, Black' lines -> {"Color": {"color_blue": "Blue", ...}} with stable ids.
    Ids already used for the same label in `existing` are reused so renames of other values never
    change identifiers."""
    existing = existing or {}
    out, errors = {}, []
    for raw in (text or '').splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if ':' not in raw:
            errors.append(f'Option line "{raw[:30]}" must look like "Color: Blue, Black".')
            continue
        group, values = raw.split(':', 1)
        group = group.strip()[:60]
        if not group or group in out:
            errors.append(f'Duplicate or empty option name "{group}".')
            continue
        old = {lbl.lower(): vid for vid, lbl in (existing.get(group) or {}).items()}
        used, vals = set(), {}
        for label in [v.strip()[:80] for v in values.split(',') if v.strip()]:
            vid = old.get(label.lower()) or f'{slugify(group)}_{slugify(label)}'
            if not slugify(label):
                errors.append(f'Invalid option value "{label}".')
                continue
            if vid in used:
                continue
            used.add(vid)
            vals[vid] = label
        if not vals:
            errors.append(f'Option "{group}" needs at least one value.')
        out[group] = vals
    if len(out) > 4:
        errors.append('At most 4 option groups are supported.')
    combos = 1
    for v in out.values():
        combos *= max(1, len(v))
    if combos > 200:
        errors.append('Too many variant combinations (max 200).')
    return out, errors


def options_to_text(options):
    return '\n'.join(f'{g}: ' + ', '.join(vals.values()) for g, vals in (options or {}).items())


def combo_key(combo):
    """combo: list of (group, value_id) -> stable key, independent of group order."""
    return '|'.join(f'{g}={v}' for g, v in sorted(combo))


def _variant_in_use(variant_id):
    return bool(OrderItem.query.filter_by(variant_id=variant_id).first()
                or CartItem.query.filter_by(variant_id=variant_id).first())


# ------------------------------------------------------------------ main save
def _int(form, key, default=0):
    try:
        return int(str(form.get(key, default)).strip() or default)
    except ValueError:
        return None


def save_product(product, form, files, actor=None):
    """Validate everything first; apply only when there are no errors. Returns (product, errors)."""
    errors = []
    is_new = product is None
    name = (form.get('name') or '').strip()
    if not name:
        errors.append('Name is required.')
    price = to_decimal(form.get('price'))
    if price is None or price < 0:
        errors.append('A valid price (0 or more) is required.')
    sale_price = to_decimal(form.get('sale_price'))
    if (form.get('sale_price') or '').strip() and sale_price is None:
        errors.append('Sale price is not a valid number.')
    if sale_price is not None and price is not None and not (0 <= sale_price < price):
        errors.append('Sale price must be lower than the regular price.')
    status = form.get('status') or 'published'
    if status not in PRODUCT_STATUSES:
        errors.append('Invalid status.')
    sku = (form.get('sku') or '').strip()[:64] or None
    brand = (form.get('brand') or '').strip()[:80]
    description = (form.get('description') or '').strip()

    pid = product.id if product else None
    if sku:
        clash = Product.query.filter(Product.sku == sku, Product.id != (pid or 0)).first()
        own_variants = [v.id for v in product.variants] if product else []
        vclash = ProductVariant.query.filter(ProductVariant.sku == sku,
                                             ~ProductVariant.id.in_(own_variants or [0])).first()
        if clash or vclash:
            errors.append(f'SKU "{sku}" is already in use.')

    options, opt_errors = parse_options(form.get('options', ''), product.options if product else None)
    errors += opt_errors

    # categories
    cat_ids = []
    for raw in form.getlist('category_ids'):
        if raw.isdigit():
            cat_ids.append(int(raw))
    primary_id = form.get('category_id', type=int)
    if primary_id and primary_id not in cat_ids:
        cat_ids.append(primary_id)
    cats = Category.query.filter(Category.id.in_(cat_ids)).all() if cat_ids else []
    if len(cats) != len(set(cat_ids)):
        errors.append('One of the selected categories does not exist.')

    # variants input
    simple_stock = _int(form, 'stock', 0)
    if not options and (simple_stock is None or simple_stock < 0):
        errors.append('Stock must be a whole number of 0 or more.')
    variant_inputs = {}
    if options and product:
        seen_skus = set()
        for v in product.variants:
            if f'v_{v.id}_stock' not in form:
                continue
            vstock = _int(form, f'v_{v.id}_stock', 0)
            vprice = to_decimal(form.get(f'v_{v.id}_price'))
            vsale = to_decimal(form.get(f'v_{v.id}_sale_price'))
            vsku = (form.get(f'v_{v.id}_sku') or '').strip()[:80] or None
            if vstock is None or vstock < 0:
                errors.append(f'Variant {v.label or v.id}: stock must be a whole number of 0 or more.')
            if (vprice is not None and vprice < 0) or (vsale is not None and vsale < 0):
                errors.append(f'Variant {v.label or v.id}: prices cannot be negative.')
            if vsale is not None and vsale >= (vprice if vprice is not None else (price or Decimal('0'))):
                errors.append(f'Variant {v.label or v.id}: sale price must be lower than its price.')
            if vsku:
                if vsku in seen_skus:
                    errors.append(f'Duplicate variant SKU "{vsku}".')
                seen_skus.add(vsku)
                other = ProductVariant.query.filter(ProductVariant.sku == vsku, ProductVariant.id != v.id).first()
                if other or Product.query.filter_by(sku=vsku).first():
                    errors.append(f'Variant SKU "{vsku}" is already in use.')
            variant_inputs[v.id] = dict(stock=vstock, price=vprice, sale_price=vsale, sku=vsku,
                                        is_active=bool(form.get(f'v_{v.id}_active')))

    # images (validated before anything is stored in the DB)
    new_images = []
    try:
        for f in files.getlist('images'):
            if f and f.filename:
                new_images.append((save_image(f, 'products'), form.get('new_image_alt', '').strip()[:200] or name))
        for line in (form.get('new_image_urls') or '').splitlines():
            if line.strip():
                new_images.append((validate_image_url(line), form.get('new_image_alt', '').strip()[:200] or name))
    except UploadError as e:
        errors.append(str(e))

    if errors:
        return product, errors

    # ---------------- apply
    if is_new:
        product = Product(name=name, slug=unique_slug(Product, name, max_len=150), price=price)
        db.session.add(product)
    elif product.name != name and not product.sku == '':
        pass  # slug stays stable for SEO even if the name changes
    product.name, product.price, product.sale_price = name, price, sale_price
    product.status, product.sku, product.brand, product.description = status, sku, brand, description
    old_options = product.options or {}
    product.options = options
    product.categories = cats
    primary = next((c for c in cats if c.id == primary_id), cats[0] if cats else None)
    product.category_id = primary.id if primary else None
    db.session.flush()

    _apply_tags_attributes(product, form)
    _sync_variants(product, options, simple_stock or 0, variant_inputs, sku)
    _apply_images(product, form, new_images)
    db.session.flush()
    product.refresh_price_cache()
    return product, []


def _apply_tags_attributes(product, form):
    from ..models import Tag
    tags = []
    ids = [int(i) for i in form.getlist('tag_ids') if str(i).isdigit()]
    if ids:
        tags += Tag.query.filter(Tag.id.in_(ids)).all()
    typed = (form.get('new_tags') or '') + ',' + (form.get('tags') or '')
    for t in typed.replace('\n', ',').replace(';', ',').split(','):
        tag = get_or_create_tag(t) if t.strip() else None
        if tag and tag not in tags:
            tags.append(tag)
    product.tags = tags
    for pav in list(product.attribute_values):
        db.session.delete(pav)
    db.session.flush()
    seen = set()
    for line in (form.get('attributes') or '').splitlines():
        if ':' not in line:
            continue
        name, values = line.split(':', 1)
        attr = get_or_create_attribute(name) if name.strip() else None
        if not attr:
            continue
        for val in [v.strip()[:100] for v in values.split(',') if v.strip()]:
            vslug = slugify(val)[:110]
            if vslug and (attr.id, vslug) not in seen:
                seen.add((attr.id, vslug))
                db.session.add(ProductAttributeValue(product_id=product.id, attribute_id=attr.id,
                                                     value=val, value_slug=vslug))


def _unique_variant_sku(base):
    sku, i = base, 1
    while ProductVariant.query.filter_by(sku=sku).first() or Product.query.filter_by(sku=sku).first():
        i += 1
        sku = f'{base}-{i}'
    return sku[:80]


def _sync_variants(product, options, simple_stock, inputs, base_sku):
    by_key = {v.option_key: v for v in product.variants}
    groups = list(options.items())
    wanted = {}
    if groups:
        for combo in itertools.product(*[[(g, vid, lbl) for vid, lbl in vals.items()] for g, vals in groups]):
            key = combo_key([(g, vid) for g, vid, _ in combo])
            wanted[key] = combo
    else:
        wanted[''] = ()
    base = base_sku or f'P{product.id}'
    pos = 0
    for key, combo in wanted.items():
        v = by_key.get(key)
        if v is None:
            suffix = '-'.join(vid for _, vid, _ in combo)
            v = ProductVariant(product_id=product.id, option_key=key, stock=0,
                               sku=_unique_variant_sku(f'{base}-{suffix}' if suffix else base))
            db.session.add(v)
            product.variants.append(v)
        pos += 1
        v.position = pos
        v.is_active = True
        if not combo:  # simple product -> default variant carries the stock
            v.stock = max(simple_stock, v.reserved or 0)
            if base_sku:
                v.sku = base_sku if not ProductVariant.query.filter(
                    ProductVariant.sku == base_sku, ProductVariant.id != (v.id or 0)).first() else v.sku
        else:
            inp = inputs.get(v.id) if v.id else None
            if inp:
                v.stock = max(inp['stock'], v.reserved or 0)
                v.price, v.sale_price = inp['price'], inp['sale_price']
                v.is_active = inp['is_active']
                if inp['sku']:
                    v.sku = inp['sku']
        db.session.flush()
        # option links (labels refreshed so facets show current labels)
        existing = {o.group_key: o for o in v.option_links}
        for g, vid, lbl in combo:
            o = existing.pop(g, None)
            if o is None:
                db.session.add(VariantOption(variant_id=v.id, group_key=g, value_key=vid, value_label=lbl))
            else:
                o.value_key, o.value_label = vid, lbl
        for stale in existing.values():
            db.session.delete(stale)
    for key, v in by_key.items():
        if key not in wanted:  # combination no longer offered
            if _variant_in_use(v.id):
                v.is_active = False
            else:
                db.session.delete(v)
    db.session.flush()


def _apply_images(product, form, new_images):
    for img in list(product.images):
        if form.get(f'img_{img.id}_delete'):
            db.session.delete(img)
            product.images.remove(img)
            continue
        img.alt_text = (form.get(f'img_{img.id}_alt') or img.alt_text or '')[:200]
        try:
            img.position = int(form.get(f'img_{img.id}_pos', img.position))
        except ValueError:
            pass
    start = max([i.position for i in product.images] + [0]) + 1
    for n, (url, alt) in enumerate(new_images):
        product.images.append(ProductImage(url=url, alt_text=alt, position=start + n))
    db.session.flush()
    chosen = form.get('primary_image', '')
    imgs = sorted(product.images, key=lambda i: (i.position, i.id or 0))
    for i in imgs:
        i.is_primary = False
    target = next((i for i in imgs if str(i.id) == chosen), imgs[0] if imgs else None)
    if target:
        target.is_primary = True
    for n, i in enumerate(imgs):
        i.position = n


# ------------------------------------------------------------------ lifecycle
def delete_or_archive(product):
    """Safe deletion: products referenced by orders are archived (history preserved)."""
    if OrderItem.query.filter_by(product_id=product.id).first():
        product.status = 'archived'
        db.session.commit()
        return 'archived'
    CartItem.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.commit()
    return 'deleted'
