"""Payment orchestration: payment records, redirect, server-side verification, duplicate-callback safety."""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from flask import current_app, url_for
from sqlalchemy import update

from ...extensions import db
from ...models import Payment, Order, StoreSettings
from .base import PaymentGateway, PaymentInit, PaymentVerify
from .mock import MockGateway

log = logging.getLogger(__name__)
_GATEWAYS = {}


class PaymentError(Exception):
    pass


def register_gateway(name, factory):
    _GATEWAYS[name] = factory


def _zarinpal_factory(app):
    from .zarinpal import ZarinpalGateway
    return ZarinpalGateway(app.config['ZARINPAL_MERCHANT_ID'], app.config.get('ZARINPAL_SANDBOX', False))


register_gateway('mock', lambda app: MockGateway())
register_gateway('zarinpal', _zarinpal_factory)


def get_gateway():
    app = current_app._get_current_object()
    gw = app.extensions.get('payment_gateway')
    if gw is None:
        name = app.config.get('PAYMENT_GATEWAY', 'mock')
        if name not in _GATEWAYS:
            raise PaymentError(f'Unknown payment gateway "{name}"')
        gw = app.extensions['payment_gateway'] = _GATEWAYS[name](app)
    return gw


def _currency():
    s = StoreSettings.query.first()
    return s.currency if s else 'USD'


def gateway_available():
    try:
        gw = get_gateway()
    except Exception:
        return False
    return (not gw.currencies) or _currency() in gw.currencies


def gateway_amount(order):
    """Integer amount in Rials. Zarinpal charges Rials; stores priced in Toman (IRT) are x10."""
    total = Decimal(order.total_amount)
    cur = order.currency or _currency()
    amount = total * 10 if cur == 'IRT' else total
    if amount != amount.to_integral_value():
        raise PaymentError('Order total must be a whole amount to be charged online.')
    if amount <= 0:
        raise PaymentError('Order total must be greater than zero.')
    return int(amount)


def callback_url():
    base = (current_app.config.get('SITE_URL') or '').rstrip('/')
    path = url_for('payment.callback')
    return f'{base}{path}' if base else url_for('payment.callback', _external=True)


def start_payment(order):
    """Create a Payment and ask the gateway for a redirect URL. Returns the Payment (status pending/failed)."""
    if order.payment_method != 'online' or order.status != 'pending' or order.payment_status != 'unpaid':
        raise PaymentError('This order cannot be paid online.')
    if order.reserved_until and order.reserved_until < datetime.utcnow():
        raise PaymentError('The payment window for this order has expired.')
    gw = get_gateway()
    amount = gateway_amount(order)
    pay = Payment(order_id=order.id, gateway=gw.name, amount=order.total_amount, gateway_amount=amount, status='pending')
    db.session.add(pay)
    db.session.commit()
    init = gw.request(amount, callback_url(), f'Order #{order.id}', mobile=order.ship_phone or order.user.phone,
                      order_id=order.id)
    if not init.ok:
        pay.status, pay.error_code, pay.error_message = 'failed', (init.error_code or '')[:20], (init.error_message or '')[:300]
        db.session.commit()
        return pay, None
    pay.authority = init.authority
    db.session.commit()
    return pay, init.redirect_url


def handle_callback(authority, status):
    """Process the browser return from the gateway. Returns (outcome, order) where outcome is one of
    paid | already_paid | cancelled | failed | error | processing | unknown | paid_needs_refund."""
    from ..orders import mark_order_paid
    pay = Payment.query.filter_by(authority=authority).first() if authority else None
    if pay is None:
        return 'unknown', None
    order = db.session.get(Order, pay.order_id)
    if pay.status == 'paid':
        return 'already_paid', order
    if (status or '').upper() != 'OK':
        db.session.execute(update(Payment).where(Payment.id == pay.id, Payment.status == 'pending')
                           .values(status='failed', error_code='cancelled', error_message='Cancelled by customer'))
        db.session.commit()
        return 'cancelled', order
    return _verify_and_finalize(pay, order)


def _verify_and_finalize(pay, order):
    from ..orders import mark_order_paid
    # claim the verification: only one concurrent callback proceeds (duplicate-callback protection)
    claimed = db.session.execute(update(Payment).where(
        Payment.id == pay.id, Payment.status.in_(('pending', 'failed'))
    ).values(status='verifying')).rowcount == 1
    db.session.commit()
    if not claimed:
        db.session.refresh(pay)
        return ('already_paid' if pay.status == 'paid' else 'processing'), order
    gw = get_gateway()
    result = gw.verify(pay.authority, pay.gateway_amount)  # amount comes from OUR record, never the client
    if result.ok:
        pay.status, pay.ref_id, pay.card_pan, pay.verified_at = 'paid', result.ref_id, result.card_pan, datetime.utcnow()
        pay.error_code = pay.error_message = None
        db.session.commit()
        outcome = mark_order_paid(order)
        return ('paid_needs_refund' if outcome == 'paid_needs_refund' else
                'already_paid' if outcome == 'already_paid' else 'paid'), order
    if result.retryable:  # gateway unreachable: allow another attempt / reconciliation
        pay.status = 'pending'
        pay.error_code, pay.error_message = (result.error_code or '')[:20], (result.error_message or '')[:300]
        db.session.commit()
        return 'error', order
    pay.status, pay.error_code, pay.error_message = 'failed', (result.error_code or '')[:20], (result.error_message or '')[:300]
    db.session.commit()
    return 'failed', order


def reconcile_pending(older_than_minutes=10, limit=100):
    """Re-verify payments stuck in pending/verifying (e.g. callback lost). Returns number finalized as paid."""
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    rows = (Payment.query.filter(Payment.status.in_(('pending', 'verifying')), Payment.authority.isnot(None),
                                 Payment.updated_at < cutoff,
                                 Payment.created_at > datetime.utcnow() - timedelta(days=2)).limit(limit).all())
    paid = 0
    for p in rows:
        db.session.execute(update(Payment).where(Payment.id == p.id, Payment.status == 'verifying')
                           .values(status='pending'))
        db.session.commit()
        db.session.refresh(p)
        outcome, _ = _verify_and_finalize(p, db.session.get(Order, p.order_id))
        paid += outcome in ('paid', 'already_paid')
    return paid
