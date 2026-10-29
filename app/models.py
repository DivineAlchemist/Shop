from datetime import datetime
from decimal import Decimal
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, Index, CheckConstraint
from .extensions import db, bcrypt

# ---------------------------------------------------------------- constants
PRODUCT_STATUSES = ('draft', 'published', 'archived')
ORDER_STATUSES = ('pending', 'preparing', 'shipped', 'received', 'cancelled', 'failed')
PAYMENT_STATUSES = ('unpaid', 'paid', 'failed', 'refunded')
# allowed order-processing transitions (shipment is part of the same flow)
ORDER_TRANSITIONS = {
    'pending': ('preparing', 'cancelled', 'failed'),
    'preparing': ('shipped', 'cancelled'),
    'shipped': ('received',),
    'received': (),
    'cancelled': (),
    'failed': (),
}


def utcnow():
    return datetime.utcnow()


# ---------------------------------------------------------------- users
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(12), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='customer', nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    phone_verified = db.Column(db.Boolean, default=False, nullable=False)
    sms_marketing_consent = db.Column(db.Boolean, default=False, nullable=False)
    marketing_consent_at = db.Column(db.DateTime)
    marketing_opt_out_at = db.Column(db.DateTime)
    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)

    cart_items = db.relationship('CartItem', backref='user', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='user', lazy=True, foreign_keys='Order.user_id')
    addresses = db.relationship('Address', backref='user', lazy=True, cascade='all, delete-orphan',
                                order_by='Address.id')

    @property
    def is_active(self):  # Flask-Login hook
        return self.is_active_account

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_staff(self):
        return self.role in ('staff', 'admin')

    def is_admin(self):
        return self.role == 'admin'

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > utcnow())


class Address(db.Model):
    __tablename__ = 'addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    label = db.Column(db.String(50), default='')
    recipient_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(80), default='')
    address_line = db.Column(db.Text, nullable=False)
    postal_code = db.Column(db.String(20), default='')
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    def as_text(self):
        parts = [self.address_line, self.city, self.postal_code]
        return ', '.join(p for p in parts if p)


# ---------------------------------------------------------------- catalog
product_categories = db.Table(
    'product_categories',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_product_categories_category', 'category_id'),
)

product_tags = db.Table(
    'product_tags',
    db.Column('product_id', db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Index('ix_product_tags_tag', 'tag_id'),
)


class Category(db.Model):
    __tablename__ = 'categories'
    __table_args__ = (UniqueConstraint('parent_id', 'name', name='uq_categories_parent_name'),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    visible = db.Column(db.Boolean, default=True, nullable=False)
    image_url = db.Column(db.String(300), default='')
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), index=True)
    path = db.Column(db.String(500), default='', index=True)  # materialized path, e.g. "/1/4/9/"
    depth = db.Column(db.Integer, default=0, nullable=False)
    is_internal = db.Column(db.Boolean, default=False, nullable=False)
    public_effective = db.Column(db.Boolean, default=True, nullable=False, index=True)
    description = db.Column(db.Text, default='')
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    parent = db.relationship('Category', remote_side=[id], backref=db.backref('children', lazy=True,
                             order_by='Category.sort_order, Category.name'))
    products = db.relationship('Product', backref='category', lazy=True, foreign_keys='Product.category_id')

    def __repr__(self):
        return self.name

    def ancestors(self):
        ids = [int(i) for i in (self.path or '').strip('/').split('/') if i and int(i) != self.id]
        if not ids:
            return []
        rows = {c.id: c for c in Category.query.filter(Category.id.in_(ids)).all()}
        return [rows[i] for i in ids if i in rows]


class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False)


class Attribute(db.Model):
    __tablename__ = 'attributes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False)


class ProductAttributeValue(db.Model):
    __tablename__ = 'product_attribute_values'
    __table_args__ = (
        UniqueConstraint('product_id', 'attribute_id', 'value_slug', name='uq_pav'),
        Index('ix_pav_attr_value', 'attribute_id', 'value_slug'),
    )
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('attributes.id'), nullable=False)
    value = db.Column(db.String(100), nullable=False)
    value_slug = db.Column(db.String(110), nullable=False)
    attribute = db.relationship('Attribute')


class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        Index('ix_products_status_created', 'status', 'created_at'),
        CheckConstraint('price >= 0', name='ck_products_price'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    brand = db.Column(db.String(80), default='', index=True)
    sku = db.Column(db.String(64), unique=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    sale_price = db.Column(db.Numeric(12, 2))
    min_price = db.Column(db.Numeric(12, 2), index=True)  # cached lowest effective price (for sort/filter)
    status = db.Column(db.String(12), default='published', nullable=False, index=True)
    # {"Color": {"color_blue": "Blue"}, "Size": {"size_m": "M"}}  (definitions only; stock lives on variants)
    options = db.Column(db.JSON, default=dict)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), index=True)  # primary category
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    categories = db.relationship('Category', secondary=product_categories, lazy=True,
                                 backref=db.backref('all_products', lazy=True))
    images = db.relationship('ProductImage', backref='product', lazy=True, cascade='all, delete-orphan',
                             order_by='ProductImage.position, ProductImage.id')
    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade='all, delete-orphan',
                               order_by='ProductVariant.position, ProductVariant.id')
    tags = db.relationship('Tag', secondary=product_tags, lazy=True, backref='products')
    attribute_values = db.relationship('ProductAttributeValue', backref='product', lazy=True,
                                       cascade='all, delete-orphan')

    def __repr__(self):
        return self.name

    # --- compat helpers (old code/templates used is_active / stock / image_url)
    @property
    def is_active(self):
        return self.status == 'published'

    @is_active.setter
    def is_active(self, value):
        self.status = 'published' if value else 'draft'

    @property
    def primary_image(self):
        imgs = self.images
        for i in imgs:
            if i.is_primary:
                return i
        return imgs[0] if imgs else None

    @property
    def image_url(self):
        img = self.primary_image
        return img.url if img else ''

    @property
    def active_variants(self):
        return [v for v in self.variants if v.is_active]

    @property
    def has_options(self):
        return bool(self.options)

    @property
    def stock(self):
        """Total purchasable units across active variants."""
        return sum(v.available for v in self.active_variants)

    @property
    def unit_price(self):
        return self.sale_price if (self.sale_price is not None and self.sale_price < self.price) else self.price

    @property
    def on_sale(self):
        return self.sale_price is not None and self.sale_price < self.price

    def refresh_price_cache(self):
        prices = [v.unit_price for v in self.active_variants] or [self.unit_price]
        self.min_price = min(prices)


class ProductImage(db.Model):
    __tablename__ = 'product_images'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    url = db.Column(db.String(400), nullable=False)
    alt_text = db.Column(db.String(200), default='')
    position = db.Column(db.Integer, default=0, nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)


class ProductVariant(db.Model):
    """A real purchasable unit. Simple products have exactly one default variant (no options)."""
    __tablename__ = 'product_variants'
    __table_args__ = (
        UniqueConstraint('product_id', 'option_key', name='uq_variant_product_optionkey'),
        CheckConstraint('stock >= 0', name='ck_variant_stock'),
        CheckConstraint('reserved >= 0', name='ck_variant_reserved'),
    )
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    sku = db.Column(db.String(80), unique=True)
    option_key = db.Column(db.String(300), default='', nullable=False)  # sorted "group=value|group=value"
    price = db.Column(db.Numeric(12, 2))        # optional override
    sale_price = db.Column(db.Numeric(12, 2))   # optional override
    stock = db.Column(db.Integer, default=0, nullable=False)     # on hand
    reserved = db.Column(db.Integer, default=0, nullable=False)  # held by unpaid/uncommitted orders
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)

    option_links = db.relationship('VariantOption', backref='variant', lazy=True, cascade='all, delete-orphan')

    @property
    def available(self):
        return max(0, (self.stock or 0) - (self.reserved or 0))

    @property
    def options_map(self):
        return {o.group_key: o.value_key for o in self.option_links}

    @property
    def options_labels(self):
        """{"Color": "Blue", "Size": "M"} using the product's current definitions."""
        defs = self.product.options or {}
        out = {}
        for o in self.option_links:
            out[o.group_key] = (defs.get(o.group_key) or {}).get(o.value_key, o.value_key)
        return out

    @property
    def label(self):
        return ' / '.join(self.options_labels.values())

    @property
    def base_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def unit_price(self):
        base = self.base_price
        sale = self.sale_price if self.sale_price is not None else (
            self.product.sale_price if self.price is None else None)
        return sale if (sale is not None and sale < base) else base


class VariantOption(db.Model):
    __tablename__ = 'variant_options'
    __table_args__ = (
        UniqueConstraint('variant_id', 'group_key', name='uq_variant_group'),
        Index('ix_variant_options_lookup', 'group_key', 'value_key'),
    )
    id = db.Column(db.Integer, primary_key=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    group_key = db.Column(db.String(60), nullable=False)
    value_key = db.Column(db.String(80), nullable=False)
    value_label = db.Column(db.String(80), default='')


# ---------------------------------------------------------------- cart / orders
class CartItem(db.Model):
    __tablename__ = 'cart_items'
    __table_args__ = (UniqueConstraint('user_id', 'variant_id', name='uq_cart_user_variant'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), index=True)
    quantity = db.Column(db.Integer, default=1)

    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')

    @property
    def unit_price(self):
        return self.variant.unit_price if self.variant else self.product.unit_price


class ShippingMethod(db.Model):
    __tablename__ = 'shipping_methods'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(200), default='')
    price = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    free_over = db.Column(db.Numeric(12, 2))  # free shipping when subtotal >= this
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)


class Coupon(db.Model):
    __tablename__ = 'coupons'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    kind = db.Column(db.String(10), default='percent', nullable=False)  # percent | fixed
    value = db.Column(db.Numeric(12, 2), nullable=False)
    min_subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    max_discount = db.Column(db.Numeric(12, 2))
    usage_limit = db.Column(db.Integer)
    per_user_limit = db.Column(db.Integer)
    used_count = db.Column(db.Integer, default=0, nullable=False)
    starts_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = (Index('ix_orders_status_created', 'status', 'created_at'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    payment_status = db.Column(db.String(20), default='unpaid', nullable=False)
    payment_method = db.Column(db.String(20), default='cod', nullable=False)  # online | cod
    subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    discount_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    shipping_total = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    currency = db.Column(db.String(8), default='USD')
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'))
    coupon_code = db.Column(db.String(40))
    shipping_method_code = db.Column(db.String(30))
    shipping_method_name = db.Column(db.String(80))
    shipping_address = db.Column(db.Text, default='')
    ship_name = db.Column(db.String(100), default='')
    ship_phone = db.Column(db.String(20), default='')
    ship_city = db.Column(db.String(80), default='')
    ship_postal_code = db.Column(db.String(20), default='')
    shipment_provider = db.Column(db.String(80))
    tracking_code = db.Column(db.String(80))
    reserved_until = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    preparing_at = db.Column(db.DateTime)
    shipped_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    history = db.relationship('OrderStatusHistory', backref='order', lazy=True, cascade='all, delete-orphan',
                              order_by='OrderStatusHistory.id')
    payments = db.relationship('Payment', backref='order', lazy=True, order_by='Payment.id')
    coupon = db.relationship('Coupon')

    def allowed_next(self):
        return ORDER_TRANSITIONS.get(self.status, ())


class OrderItem(db.Model):
    """Immutable purchase-time snapshot (name/sku/options/price) + stock-state bookkeeping."""
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'))
    quantity = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Numeric(12, 2), nullable=False)
    product_name = db.Column(db.String(150), default='')
    sku = db.Column(db.String(80), default='')
    variant_label = db.Column(db.String(200), default='')
    options_snapshot = db.Column(db.JSON, default=dict)
    # reserved -> deducted -> (restored) ; reserved -> released
    stock_state = db.Column(db.String(12), default='reserved', nullable=False)

    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')

    @property
    def unit_price(self):
        return self.price_at_purchase

    @property
    def line_total(self):
        return self.price_at_purchase * self.quantity

    @property
    def display_name(self):
        return self.product_name or (self.product.name if self.product else 'Product')


class OrderStatusHistory(db.Model):
    __tablename__ = 'order_status_history'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    from_status = db.Column(db.String(20))
    to_status = db.Column(db.String(20), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    note = db.Column(db.String(300), default='')
    created_at = db.Column(db.DateTime, default=utcnow)
    changed_by = db.relationship('User')


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    gateway = db.Column(db.String(20), nullable=False)
    authority = db.Column(db.String(64), unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)       # in store currency
    gateway_amount = db.Column(db.Integer, nullable=False)       # integer amount sent to gateway (Rials)
    status = db.Column(db.String(12), default='pending', nullable=False)  # pending|verifying|paid|failed
    ref_id = db.Column(db.String(64))
    card_pan = db.Column(db.String(32))
    error_code = db.Column(db.String(20))
    error_message = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    verified_at = db.Column(db.DateTime)


# ---------------------------------------------------------------- SMS / verification
class SmsLog(db.Model):
    __tablename__ = 'sms_logs'
    id = db.Column(db.Integer, primary_key=True)
    dedupe_key = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    purpose = db.Column(db.String(40), nullable=False)
    template = db.Column(db.String(40))
    body = db.Column(db.Text, default='')
    status = db.Column(db.String(10), default='queued', nullable=False, index=True)  # queued|sent|failed
    provider = db.Column(db.String(20))
    provider_message_id = db.Column(db.String(40))
    attempts = db.Column(db.Integer, default=0, nullable=False)
    error = db.Column(db.String(300))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    sent_at = db.Column(db.DateTime)


class VerificationCode(db.Model):
    __tablename__ = 'verification_codes'
    __table_args__ = (Index('ix_vc_phone_purpose', 'phone', 'purpose', 'created_at'),)
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)  # register | reset
    code_hash = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    consumed_at = db.Column(db.DateTime)


# ---------------------------------------------------------------- store config / merchandising
class StoreSettings(db.Model):
    """Single-row store configuration. Secrets (API keys) are NEVER stored here."""
    __tablename__ = 'store_settings'
    id = db.Column(db.Integer, primary_key=True)
    store_name = db.Column(db.String(100), default='Raven', nullable=False)
    description = db.Column(db.Text, default='')
    logo_url = db.Column(db.String(300), default='')
    favicon_url = db.Column(db.String(300), default='')
    domain = db.Column(db.String(120), default='')
    contact_email = db.Column(db.String(120), default='')
    contact_phone = db.Column(db.String(30), default='')
    address = db.Column(db.Text, default='')
    banner_image_url = db.Column(db.String(300), default='')
    banner_title = db.Column(db.String(150), default='')
    banner_link = db.Column(db.String(300), default='')
    social_links = db.Column(db.JSON, default=dict)  # {"instagram": url, ...}
    currency = db.Column(db.String(8), default='USD', nullable=False)
    locale = db.Column(db.String(8), default='en', nullable=False)
    shipping_info = db.Column(db.Text, default='')
    return_policy = db.Column(db.Text, default='')
    seo_title = db.Column(db.String(150), default='')
    seo_description = db.Column(db.String(300), default='')
    seo_keywords = db.Column(db.String(300), default='')
    og_image_url = db.Column(db.String(300), default='')
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class HomepageSection(db.Model):
    __tablename__ = 'homepage_sections'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), default='')  # empty -> the source category's name is shown
    description = db.Column(db.String(300), default='')
    auto_scroll = db.Column(db.Boolean, default=False, nullable=False)
    scroll_interval = db.Column(db.Integer, default=5, nullable=False)  # seconds
    source_category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))  # NULL = all public products
    include_subcategories = db.Column(db.Boolean, default=True, nullable=False)
    product_limit = db.Column(db.Integer, default=10, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    visible = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    source_category = db.relationship('Category')

    @property
    def display_title(self):
        if (self.title or '').strip():
            return self.title.strip()
        return self.source_category.name if self.source_category else 'New arrivals'


BANNER_LINK_TYPES = ('none', 'product', 'category', 'url')


class Banner(db.Model):
    """Homepage slider slide. Links to a product, a category or a custom URL."""
    __tablename__ = 'banners'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), default='')
    subtitle = db.Column(db.String(300), default='')
    button_text = db.Column(db.String(40), default='')
    image_url = db.Column(db.String(400), nullable=False)
    link_type = db.Column(db.String(10), default='none', nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='SET NULL'))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'))
    url = db.Column(db.String(400), default='')
    position = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    autoplay_seconds = db.Column(db.Integer, default=5, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    product = db.relationship('Product')
    category = db.relationship('Category')


# ---------------------------------------------------------------- engagement
class WishlistItem(db.Model):
    __tablename__ = 'wishlist_items'
    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='uq_wishlist'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    product = db.relationship('Product')


class Review(db.Model):
    __tablename__ = 'reviews'
    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='uq_review_user_product'),
                      CheckConstraint('rating BETWEEN 1 AND 5', name='ck_review_rating'))
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, default='')
    verified_purchase = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship('User')
    product = db.relationship('Product', backref=db.backref('reviews', lazy=True, cascade='all, delete-orphan'))
