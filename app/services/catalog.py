"""Catalog queries: category tree, visibility rules, search/filter/sort/pagination, homepage sections.

Visibility rule (single source of truth, used by browse, search, product pages, sitemap and
homepage sections): a product is publicly visible iff it is *published* AND (it has no category
OR it belongs to at least one publicly visible category). A category is publicly visible iff it is
`visible`, not `is_internal`, and all its ancestors are too (stored in `public_effective`).
"""
from dataclasses import dataclass, field
from sqlalchemy import and_, or_, exists, select, func, literal
from sqlalchemy.orm import selectinload, joinedload

from ..extensions import db
from ..models import (Category, Product, ProductVariant, VariantOption, Tag, Attribute,
                      ProductAttributeValue, product_categories, product_tags, HomepageSection)
from ..utils import escape_like, slugify, to_decimal

MAX_CATEGORY_DEPTH = 20
SORTS = {
    'newest': (Product.created_at.desc(), Product.id.desc()),
    'price_asc': (Product.min_price.asc(), Product.id.desc()),
    'price_desc': (Product.min_price.desc(), Product.id.desc()),
    'name': (Product.name.asc(), Product.id.asc()),
}
SORT_LABELS = {'newest': 'Newest', 'price_asc': 'Price: low to high',
               'price_desc': 'Price: high to low', 'name': 'Name A–Z'}


# ------------------------------------------------------------------ categories
def rebuild_subtree(cat):
    """Recompute path/depth/public_effective for `cat` and everything below it."""
    if cat.id is None:
        db.session.flush()
    parent = cat.parent
    cat.path = (parent.path if parent else '/') + f'{cat.id}/'
    cat.depth = (parent.depth + 1) if parent else 0
    parent_public = parent.public_effective if parent else True
    cat.public_effective = bool(cat.visible and not cat.is_internal and parent_public)
    stack = list(cat.children)
    while stack:
        c = stack.pop()
        c.path = c.parent.path + f'{c.id}/'
        c.depth = c.parent.depth + 1
        c.public_effective = bool(c.visible and not c.is_internal and c.parent.public_effective)
        stack.extend(c.children)


def validate_parent(cat, parent_id):
    """Return (parent|None, error). Prevents self/descendant parents (cycles) and absurd depth."""
    if not parent_id:
        return None, None
    parent = db.session.get(Category, parent_id)
    if parent is None:
        return None, 'Parent category does not exist.'
    if cat is not None and cat.id is not None:
        if parent.id == cat.id:
            return None, 'A category cannot be its own parent.'
        if (parent.path or '').startswith(cat.path or f'/{cat.id}/'):
            return None, 'A category cannot be moved under one of its own descendants.'
    if parent.depth + 1 >= MAX_CATEGORY_DEPTH:
        return None, 'Maximum category depth reached.'
    return parent, None


def get_category(slug=None, id=None, allow_internal=False):
    q = Category.query
    q = q.filter_by(slug=slug) if slug else q.filter_by(id=id)
    cat = q.first()
    if cat is None or (not cat.public_effective and not allow_internal):
        return None
    return cat


def category_tree(public_only=True):
    """Nested [{'category': c, 'children': [...]}] built from a single query (categories are few)."""
    q = Category.query.order_by(Category.depth, Category.sort_order, Category.name)
    if public_only:
        q = q.filter(Category.public_effective.is_(True))
    nodes = {c.id: {'category': c, 'children': []} for c in q.all()}
    roots = []
    for c in nodes.values():
        pid = c['category'].parent_id
        (nodes[pid]['children'] if pid in nodes else roots).append(c)
    return roots


def flat_tree(public_only=False):
    """Depth-first ordered list of (category, depth) for selects/management tables."""
    out = []

    def walk(nodes):
        for n in nodes:
            out.append((n['category'], n['category'].depth))
            walk(n['children'])
    walk(category_tree(public_only))
    return out


def breadcrumbs(cat):
    return (cat.ancestors() + [cat]) if cat else []


def _category_clause(cat, public_only=True, include_descendants=True):
    cond = [product_categories.c.product_id == Product.id]
    if include_descendants:
        cond.append(Category.path.like(escape_like(cat.path) + '%', escape='\\'))
    else:
        cond.append(Category.id == cat.id)
    if public_only:
        cond.append(Category.public_effective.is_(True))
    return select(literal(1)).select_from(
        product_categories.join(Category, Category.id == product_categories.c.category_id)
    ).where(and_(*cond)).exists()


# ------------------------------------------------------------------ visibility
def public_product_clause(include_internal=False):
    clause = Product.status == 'published'
    if include_internal:
        return clause
    has_any = select(literal(1)).select_from(product_categories).where(
        product_categories.c.product_id == Product.id).exists()
    has_public = select(literal(1)).select_from(
        product_categories.join(Category, Category.id == product_categories.c.category_id)
    ).where(and_(product_categories.c.product_id == Product.id,
                 Category.public_effective.is_(True))).exists()
    return and_(clause, or_(~has_any, has_public))


def product_by_slug(slug, include_internal=False):
    return Product.query.filter(Product.slug == slug, public_product_clause(include_internal)).first()


# ------------------------------------------------------------------ filters / search
@dataclass
class CatalogFilters:
    q: str = ''
    category: object = None
    cats: list = field(default_factory=list)       # categories picked in the filter (OR, each incl. descendants)
    tags: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)      # attribute slug -> [value slugs]
    options: dict = field(default_factory=dict)    # option group -> [value keys]
    min_price: object = None
    max_price: object = None
    in_stock: bool = False
    sort: str = 'newest'
    page: int = 1
    per_page: int = 12
    include_internal: bool = False

    @classmethod
    def from_args(cls, args, category=None, per_page=12, include_internal=False):
        f = cls(q=(args.get('q') or '').strip()[:100], category=category, per_page=per_page,
                include_internal=include_internal)
        f.tags = [t for t in args.getlist('tag') if t][:10]
        slugs = [c for c in args.getlist('cat') if c][:20]
        if slugs:
            q = Category.query.filter(Category.slug.in_(slugs))
            if not include_internal:
                q = q.filter(Category.public_effective.is_(True))
            f.cats = q.order_by(Category.depth, Category.name).all()
        slugs = [c for c in args.getlist('cat') if c][:20]
        if slugs:
            q = Category.query.filter(Category.slug.in_(slugs))
            if not include_internal:
                q = q.filter(Category.public_effective.is_(True))
            f.cats = q.order_by(Category.id).all()
        for key in args.keys():
            if key.startswith('a_'):
                f.attrs[key[2:]] = [v for v in args.getlist(key) if v][:20]
            elif key.startswith('opt_'):
                f.options[key[4:]] = [v for v in args.getlist(key) if v][:20]
        f.min_price = to_decimal(args.get('min_price'))
        f.max_price = to_decimal(args.get('max_price'))
        f.in_stock = args.get('in_stock') in ('1', 'on', 'true')
        s = args.get('sort', 'newest')
        f.sort = s if s in SORTS else 'newest'
        try:
            f.page = max(1, int(args.get('page', 1)))
        except (TypeError, ValueError):
            f.page = 1
        return f


def _search_clause(term):
    like = f'%{escape_like(term)}%'
    return or_(
        Product.name.ilike(like, escape='\\'),
        Product.description.ilike(like, escape='\\'),
        Product.brand.ilike(like, escape='\\'),
        Product.sku.ilike(like, escape='\\'),
        Product.variants.any(ProductVariant.sku.ilike(like, escape='\\')),
        Product.tags.any(Tag.name.ilike(like, escape='\\')),
        Product.attribute_values.any(ProductAttributeValue.value.ilike(like, escape='\\')),
    )


def _scope_query(f):
    """Visibility + category + text search + price/stock (everything except facet filters)."""
    q = Product.query.filter(public_product_clause(f.include_internal))
    if f.category is not None:
        q = q.filter(_category_clause(f.category, public_only=not f.include_internal))
    if f.cats:
        q = q.filter(or_(*[_category_clause(c, public_only=not f.include_internal) for c in f.cats]))
    if f.cats:
        q = q.filter(or_(*[_category_clause(c, public_only=not f.include_internal) for c in f.cats]))
    for term in f.q.split()[:6]:
        q = q.filter(_search_clause(term))
    if f.min_price is not None:
        q = q.filter(Product.min_price >= f.min_price)
    if f.max_price is not None:
        q = q.filter(Product.min_price <= f.max_price)
    if f.in_stock:
        q = q.filter(Product.variants.any(and_(ProductVariant.is_active.is_(True),
                                               ProductVariant.stock - ProductVariant.reserved > 0)))
    return q


def _facet_filtered(q, f):
    for slug in f.tags:
        q = q.filter(Product.tags.any(Tag.slug == slug))
    for attr_slug, values in f.attrs.items():
        if values:
            q = q.filter(Product.attribute_values.any(and_(
                ProductAttributeValue.value_slug.in_(values),
                ProductAttributeValue.attribute.has(Attribute.slug == attr_slug))))
    groups = {g: v for g, v in f.options.items() if v}
    if groups:  # one variant must satisfy every selected option group
        conds = [ProductVariant.is_active.is_(True)]
        for g, vals in groups.items():
            conds.append(ProductVariant.option_links.any(and_(
                VariantOption.group_key == g, VariantOption.value_key.in_(vals))))
        q = q.filter(Product.variants.any(and_(*conds)))
    return q


def product_query(f):
    return _facet_filtered(_scope_query(f), f)


def search_products(f):
    q = product_query(f).options(selectinload(Product.images), selectinload(Product.variants),
                                 joinedload(Product.category)).order_by(*SORTS[f.sort])
    return q.paginate(page=f.page, per_page=f.per_page, error_out=False)


def facets(f, limit=30):
    """Available tag/attribute/option values within the current scope (database aggregates)."""
    ids = _scope_query(f).with_entities(Product.id).subquery()
    in_scope = select(ids.c.id)
    tags = (db.session.query(Tag.slug, Tag.name, func.count(product_tags.c.product_id))
            .join(product_tags, product_tags.c.tag_id == Tag.id)
            .filter(product_tags.c.product_id.in_(in_scope))
            .group_by(Tag.id).order_by(func.count(product_tags.c.product_id).desc(), Tag.name)
            .limit(limit).all())
    attr_rows = (db.session.query(Attribute.slug, Attribute.name, ProductAttributeValue.value_slug,
                                  func.min(ProductAttributeValue.value),
                                  func.count(ProductAttributeValue.product_id))
                 .join(ProductAttributeValue, ProductAttributeValue.attribute_id == Attribute.id)
                 .filter(ProductAttributeValue.product_id.in_(in_scope))
                 .group_by(Attribute.id, ProductAttributeValue.value_slug)
                 .order_by(Attribute.name, ProductAttributeValue.value_slug).limit(limit * 4).all())
    attrs = {}
    for slug, name, vslug, vlabel, n in attr_rows:
        attrs.setdefault((slug, name), []).append((vslug, vlabel, n))
    opt_rows = (db.session.query(VariantOption.group_key, VariantOption.value_key,
                                 func.min(VariantOption.value_label),
                                 func.count(func.distinct(ProductVariant.product_id)))
                .join(ProductVariant, ProductVariant.id == VariantOption.variant_id)
                .filter(ProductVariant.is_active.is_(True), ProductVariant.product_id.in_(in_scope))
                .group_by(VariantOption.group_key, VariantOption.value_key)
                .order_by(VariantOption.group_key, VariantOption.value_key).limit(limit * 4).all())
    options = {}
    for g, k, label, n in opt_rows:
        options.setdefault(g, []).append((k, label or k, n))
    return {'tags': tags, 'attrs': attrs, 'options': options}


# ------------------------------------------------------------------ homepage sections
def section_products(section):
    """Newest-first (stable on ties) products for a section. Public visibility rules always apply,
    even when the source is an internal merchandising category."""
    q = Product.query.filter(public_product_clause(False))
    cat = section.source_category
    if section_source_missing(section):
        return []
    if cat is not None:
        q = q.filter(_category_clause(cat, public_only=False,
                                      include_descendants=section.include_subcategories))
    limit = max(1, min(int(section.product_limit or 10), 50))
    return (q.options(selectinload(Product.images), selectinload(Product.variants), joinedload(Product.category))
            .order_by(Product.created_at.desc(), Product.id.desc()).limit(limit).all())


def section_source_missing(section):
    return section.source_category_id is not None and section.source_category is None


def homepage_sections():
    sections = (HomepageSection.query.filter_by(is_active=True, visible=True)
                .order_by(HomepageSection.position, HomepageSection.id).all())
    out = []
    for s in sections:
        products = section_products(s)
        if products:
            out.append({'section': s, 'products': products})
    return out


# ------------------------------------------------------------------ tags / attributes helpers
def get_or_create_tag(name):
    name = name.strip()[:50]
    slug = slugify(name)[:60]
    if not slug:
        return None
    tag = Tag.query.filter_by(slug=slug).first()
    if tag is None:
        tag = Tag(name=name, slug=slug)
        db.session.add(tag)
        db.session.flush()
    return tag


def get_or_create_attribute(name):
    name = name.strip()[:50]
    slug = slugify(name)[:60]
    if not slug:
        return None
    attr = Attribute.query.filter_by(slug=slug).first()
    if attr is None:
        attr = Attribute(name=name, slug=slug)
        db.session.add(attr)
        db.session.flush()
    return attr


# ------------------------------------------------------------------ banners
def active_banners():
    """Active slider banners with a resolved, *publicly valid* link (internal targets are never linked)."""
    from flask import url_for
    from ..models import Banner
    out = []
    for b in Banner.query.filter_by(is_active=True).order_by(Banner.position, Banner.id).all():
        href = None
        if b.link_type == 'product' and b.product_id:
            p = Product.query.filter(Product.id == b.product_id, public_product_clause()).first()
            href = url_for('customer.product_detail', slug=p.slug) if p else None
        elif b.link_type == 'category' and b.category and b.category.public_effective:
            href = url_for('customer.category', slug=b.category.slug)
        elif b.link_type == 'url' and b.url:
            href = b.url
        out.append({'banner': b, 'href': href})
    return out
