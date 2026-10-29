"""Server-side cart validation and price calculation (never trust client-side prices)."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import CartItem, Product, Coupon, Order, ShippingMethod
from .catalog import public_product_clause

CENT = Decimal('0.01')


def money(d):
    return Decimal(d).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class CartLine:
    item: CartItem
    variant: object
    product: object
    qty: int
    unit_price: Decimal
    problem: str = None

    @property
    def line_total(self):
        return money(self.unit_price * self.qty)


@dataclass
class Quote:
    lines: list = field(default_factory=list)
    subtotal: Decimal = Decimal('0.00')
    discount: Decimal = Decimal('0.00')
    shipping: Decimal = Decimal('0.00')
    total: Decimal = Decimal('0.00')
    coupon: object = None
    method: object = None
    errors: list = field(default_factory=list)
    coupon_error: str = None


def cart_lines(user):
    items = (CartItem.query.filter_by(user_id=user.id)
             .options(joinedload(CartItem.variant), joinedload(CartItem.product)).order_by(CartItem.id).all())
    lines = []
    for it in items:
        v, p = it.variant, it.product
        problem = None
        if v is None or not v.is_active:
            problem = f'{p.name}: this option is no longer available.'
        elif not Product.query.filter(Product.id == p.id, public_product_clause()).first():
            problem = f'{p.name} is no longer available.'
        elif v.available < it.quantity:
            problem = (f'Only {v.available} of {p.name}' + (f' ({v.label})' if v.label else '') + ' left in stock.'
                       if v.available else f'{p.name}' + (f' ({v.label})' if v.label else '') + ' is out of stock.')
        price = v.unit_price if v else p.unit_price
        lines.append(CartLine(it, v, p, it.quantity, money(price), problem))
    return lines


def validate_coupon(code, user, subtotal):
    """Return (coupon, discount, error)."""
    code = (code or '').strip().upper()
    if not code:
        return None, Decimal('0.00'), None
    c = Coupon.query.filter(db.func.upper(Coupon.code) == code).first()
    now = datetime.utcnow()
    if not c or not c.is_active:
        return None, Decimal('0.00'), 'Invalid coupon code.'
    if (c.starts_at and c.starts_at > now) or (c.expires_at and c.expires_at < now):
        return None, Decimal('0.00'), 'This coupon is not currently valid.'
    if c.usage_limit is not None and c.used_count >= c.usage_limit:
        return None, Decimal('0.00'), 'This coupon has been fully redeemed.'
    if subtotal < (c.min_subtotal or 0):
        return None, Decimal('0.00'), f'Minimum order amount for this coupon is {money(c.min_subtotal)}.'
    if c.per_user_limit is not None:
        used = Order.query.filter(Order.user_id == user.id, Order.coupon_id == c.id,
                                  Order.status.notin_(('cancelled', 'failed'))).count()
        if used >= c.per_user_limit:
            return None, Decimal('0.00'), 'You have already used this coupon.'
    if c.kind == 'percent':
        disc = money(subtotal * Decimal(c.value) / 100)
    else:
        disc = money(min(Decimal(c.value), subtotal))
    if c.max_discount is not None:
        disc = min(disc, money(c.max_discount))
    return c, min(disc, subtotal), None


def shipping_methods():
    return ShippingMethod.query.filter_by(is_active=True).order_by(ShippingMethod.position, ShippingMethod.id).all()


def shipping_price(method, subtotal):
    if method is None:
        return Decimal('0.00')
    if method.free_over is not None and subtotal >= method.free_over:
        return Decimal('0.00')
    return money(method.price or 0)


def quote(user, shipping_code=None, coupon_code=None):
    q = Quote(lines=cart_lines(user))
    q.errors = [l.problem for l in q.lines if l.problem]
    q.subtotal = money(sum((l.line_total for l in q.lines), Decimal('0')))
    q.coupon, q.discount, q.coupon_error = validate_coupon(coupon_code, user, q.subtotal)
    methods = shipping_methods()
    q.method = next((m for m in methods if m.code == shipping_code), methods[0] if methods else None)
    q.shipping = shipping_price(q.method, q.subtotal - q.discount)
    q.total = money(q.subtotal - q.discount + q.shipping)
    return q
