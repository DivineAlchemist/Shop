"""Checkout, order state machine, payment completion and expiry. All state changes are
compare-and-set guarded so repeated/concurrent operations stay idempotent."""
import logging
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (Order, OrderItem, OrderStatusHistory, CartItem, Coupon, StoreSettings,
                      ORDER_TRANSITIONS)
from . import inventory, notifications
from .pricing import quote

log = logging.getLogger(__name__)


class OrderError(Exception):
    pass


class InvalidTransition(OrderError):
    pass


def _history(order, from_s, to_s, actor, note=''):
    db.session.add(OrderStatusHistory(order_id=order.id, from_status=from_s, to_status=to_s,
                                      changed_by_id=getattr(actor, 'id', None), note=note[:300]))


def store_currency():
    s = StoreSettings.query.first()
    return s.currency if s else 'USD'


def available_payment_methods():
    from .payments import gateway_available
    return ['cod'] + (['online'] if gateway_available() else [])


# ------------------------------------------------------------------ checkout
def create_order(user, address, shipping_code, coupon_code, payment_method):
    """address: dict(name, phone, city, address_line, postal_code). Returns (order, error)."""
    expire_unpaid_orders()
    q = quote(user, shipping_code, coupon_code)
    if not q.lines:
        return None, 'Your cart is empty.'
    if q.errors:
        return None, q.errors[0]
    if coupon_code and q.coupon_error:
        return None, q.coupon_error
    if payment_method not in available_payment_methods():
        return None, 'Selected payment method is not available.'
    if not (address.get('address_line') or '').strip():
        return None, 'Shipping address is required.'
    window = current_app.config['ORDER_PAYMENT_WINDOW_MINUTES']
    now = datetime.utcnow()
    try:
        order = Order(
            user_id=user.id, status='pending', payment_status='unpaid', payment_method=payment_method,
            subtotal=q.subtotal, discount_total=q.discount, shipping_total=q.shipping, total_amount=q.total,
            currency=store_currency(), coupon_id=q.coupon.id if q.coupon else None,
            coupon_code=q.coupon.code if q.coupon else None,
            shipping_method_code=q.method.code if q.method else None,
            shipping_method_name=q.method.name if q.method else None,
            shipping_address=', '.join(p for p in (address['address_line'], address.get('city'),
                                                  address.get('postal_code')) if p),
            ship_name=address.get('name') or user.name, ship_phone=address.get('phone') or user.phone,
            ship_city=address.get('city', ''), ship_postal_code=address.get('postal_code', ''),
            reserved_until=now + timedelta(minutes=window) if payment_method == 'online' else None)
        db.session.add(order)
        db.session.flush()
        for line in sorted(q.lines, key=lambda l: l.variant.id):  # stable lock order
            v, p = line.variant, line.product
            inventory.reserve(v.id, line.qty, p.name)
            db.session.add(OrderItem(
                order_id=order.id, product_id=p.id, variant_id=v.id, quantity=line.qty,
                price_at_purchase=line.unit_price, product_name=p.name, sku=v.sku or p.sku or '',
                variant_label=v.label, options_snapshot=v.options_labels, stock_state='reserved'))
        if q.coupon:
            res = db.session.execute(update(Coupon).where(
                Coupon.id == q.coupon.id,
                db.or_(Coupon.usage_limit.is_(None), Coupon.used_count < Coupon.usage_limit)
            ).values(used_count=Coupon.used_count + 1))
            if res.rowcount != 1:
                raise OrderError('This coupon has been fully redeemed.')
        CartItem.query.filter_by(user_id=user.id).delete()
        _history(order, None, 'pending', user, 'Order placed')
        db.session.commit()
    except inventory.InsufficientStock as e:
        db.session.rollback()
        return None, f'Not enough stock for {e.name}.'
    except (OrderError, IntegrityError) as e:
        db.session.rollback()
        return None, str(e) if isinstance(e, OrderError) else 'Could not place the order, please try again.'
    notifications.notify_order_placed(order)  # failure-safe; after commit
    return order, None


# ------------------------------------------------------------------ state machine
def _release_coupon(order):
    if order.coupon_id:
        db.session.execute(update(Coupon).where(Coupon.id == order.coupon_id, Coupon.used_count > 0)
                           .values(used_count=Coupon.used_count - 1))


def transition_order(order, to_status, actor=None, note='', provider=None, tracking=None):
    """Move an order along ORDER_TRANSITIONS. Raises InvalidTransition on illegal/duplicate moves."""
    from_status = order.status
    if to_status not in ORDER_TRANSITIONS.get(from_status, ()):
        raise InvalidTransition(f'Cannot move an order from "{from_status}" to "{to_status}".')
    extra = {}
    now = datetime.utcnow()
    if to_status == 'preparing':
        if order.payment_method == 'online' and order.payment_status != 'paid':
            raise InvalidTransition('This order is still awaiting online payment.')
        extra['preparing_at'] = now
    elif to_status == 'shipped':
        provider, tracking = (provider or '').strip(), (tracking or '').strip()
        if not provider or not tracking:
            raise InvalidTransition('Shipment provider and tracking code are required.')
        extra.update(shipped_at=now, shipment_provider=provider[:80], tracking_code=tracking[:80])
    elif to_status == 'received':
        extra['received_at'] = now
        if order.payment_status == 'unpaid' and order.payment_method == 'cod':
            extra.update(payment_status='paid', paid_at=now)  # cash collected on delivery
    elif to_status == 'cancelled':
        extra['cancelled_at'] = now
    elif to_status == 'failed':
        if order.payment_status == 'unpaid':
            extra['payment_status'] = 'failed'
    res = db.session.execute(update(Order).where(Order.id == order.id, Order.status == from_status)
                             .values(status=to_status, updated_at=now, **extra))
    if res.rowcount != 1:
        db.session.rollback()
        raise InvalidTransition('The order was changed by someone else; reload and retry.')
    db.session.refresh(order)
    # inventory side effects
    if to_status == 'preparing' and order.payment_method == 'cod':
        inventory.commit_order(order)  # COD: stock is deducted when staff accept the order
    elif to_status in ('cancelled', 'failed'):
        inventory.undo_order(order)
        _release_coupon(order)
        if order.payment_status == 'paid':
            note = (note + ' ' if note else '') + 'Refund required.'
    _history(order, from_status, to_status, actor, note)
    db.session.commit()
    notifications.notify_status(order, to_status)
    return order


def customer_cancel(order, user):
    if order.user_id != user.id:
        raise InvalidTransition('Not your order.')
    if order.status != 'pending' or order.payment_status != 'unpaid':
        raise InvalidTransition('This order can no longer be cancelled online; contact support.')
    return transition_order(order, 'cancelled', user, 'Cancelled by customer')


def customer_confirm_received(order, user):
    if order.user_id != user.id:
        raise InvalidTransition('Not your order.')
    return transition_order(order, 'received', user, 'Confirmed by customer')


def mark_refunded(order, actor):
    res = db.session.execute(update(Order).where(
        Order.id == order.id, Order.payment_status == 'paid', Order.status.in_(('cancelled', 'failed'))
    ).values(payment_status='refunded'))
    if res.rowcount != 1:
        db.session.rollback()
        raise InvalidTransition('Only paid orders that were cancelled or failed can be marked refunded.')
    db.session.refresh(order)
    _history(order, order.status, order.status, actor, 'Marked refunded')
    db.session.commit()


# ------------------------------------------------------------------ payment completion
def mark_order_paid(order, note='Payment verified'):
    """Called once a gateway payment is server-verified. Idempotent. Returns
    'paid' | 'already_paid' | 'paid_needs_refund'."""
    now = datetime.utcnow()
    db.session.refresh(order)
    if order.payment_status == 'paid':
        return 'already_paid'
    if order.status == 'failed':  # payment window expired while the customer was paying: try to revive
        if inventory.re_reserve_order(order):
            res = db.session.execute(update(Order).where(Order.id == order.id, Order.status == 'failed')
                                     .values(status='pending', payment_status='unpaid', updated_at=now))
            if res.rowcount == 1:
                if order.coupon_id:
                    db.session.execute(update(Coupon).where(Coupon.id == order.coupon_id)
                                       .values(used_count=Coupon.used_count + 1))
                db.session.refresh(order)
                _history(order, 'failed', 'pending', None, 'Revived: payment received after expiry')
            else:
                db.session.rollback()
                db.session.refresh(order)
    if order.status == 'pending':
        res = db.session.execute(update(Order).where(
            Order.id == order.id, Order.status == 'pending', Order.payment_status != 'paid'
        ).values(payment_status='paid', paid_at=now, reserved_until=None, updated_at=now))
        if res.rowcount == 1:
            db.session.refresh(order)
            inventory.commit_order(order)  # reserved -> deducted exactly once
            _history(order, 'pending', 'pending', None, note)
            db.session.commit()
            return 'paid'
        db.session.rollback()
        return 'already_paid'
    # order is cancelled/failed (could not revive): money received, staff must refund
    db.session.execute(update(Order).where(Order.id == order.id, Order.payment_status != 'paid')
                       .values(payment_status='paid', paid_at=now, updated_at=now))
    db.session.refresh(order)
    _history(order, order.status, order.status, None, 'Paid after order was closed. Refund required.')
    db.session.commit()
    return 'paid_needs_refund'


def expire_unpaid_orders(now=None, limit=200):
    """Fail online orders whose payment window elapsed, releasing their reservations."""
    from ..models import Payment
    now = now or datetime.utcnow()
    rows = (Order.query.filter(Order.status == 'pending', Order.payment_method == 'online',
                               Order.payment_status == 'unpaid', Order.reserved_until.isnot(None),
                               Order.reserved_until < now).limit(limit).all())
    n = 0
    for o in rows:
        if Payment.query.filter_by(order_id=o.id, status='verifying').first():
            continue  # a verification is in flight
        try:
            transition_order(o, 'failed', None, 'Payment window expired')
            n += 1
        except InvalidTransition:
            db.session.rollback()
    return n
