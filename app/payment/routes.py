import logging
from flask import render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user

from . import payment_bp
from ..extensions import db, csrf
from ..i18n import flash  # translated flash messages
from ..models import Order
from ..services import payments
from ..services.payments.mock import MockGateway

log = logging.getLogger(__name__)


@payment_bp.route('/orders/<int:order_id>/pay', methods=['GET', 'POST'])
@login_required
def pay(order_id):
    """Start (or retry) an online payment for one of the current user's orders."""
    order = db.session.get(Order, order_id) or abort(404)
    if order.user_id != current_user.id:
        abort(403)
    try:
        pay_rec, url = payments.start_payment(order)
    except payments.PaymentError as e:
        flash(str(e), 'warning')
        return redirect(url_for('customer.order_detail', order_id=order.id))
    except Exception:
        log.exception('Payment start failed for order %s', order.id)
        flash('Payment is temporarily unavailable. Please try again.', 'danger')
        return redirect(url_for('customer.order_detail', order_id=order.id))
    if not url:
        flash('Could not start the payment. Please try again.', 'danger')
        return redirect(url_for('customer.order_detail', order_id=order.id))
    return redirect(url)


@payment_bp.route('/payment/callback')
@csrf.exempt  # gateway redirects the browser here; authenticity comes from server-side verification
def callback():
    authority = request.args.get('Authority', '')
    status = request.args.get('Status', '')
    try:
        outcome, order = payments.handle_callback(authority, status)
    except Exception:
        log.exception('Payment callback failed')
        outcome, order = 'error', None
    messages = {
        'paid': ('Payment successful. Thank you!', 'success'),
        'already_paid': ('This payment was already confirmed.', 'info'),
        'cancelled': ('Payment was cancelled. You can try again from your order page.', 'warning'),
        'failed': ('Payment could not be verified. You were not charged for this order, or the charge will be refunded.', 'danger'),
        'error': ('We could not confirm the payment yet. If money was deducted it will be reconciled automatically.', 'warning'),
        'processing': ('Your payment is being confirmed. Refresh in a moment.', 'info'),
        'paid_needs_refund': ('Payment received but the order had expired; support will contact you for a refund.', 'warning'),
        'unknown': ('Unknown payment reference.', 'danger'),
    }
    msg, cat = messages.get(outcome, messages['error'])
    flash(msg, cat)
    if order is not None and current_user.is_authenticated and order.user_id == current_user.id:
        return redirect(url_for('customer.order_detail', order_id=order.id))
    return redirect(url_for('customer.orders') if current_user.is_authenticated else url_for('customer.index'))


# ---- development-only fake bank page (never available outside dev/test mock mode)
@payment_bp.route('/payment/mock/<authority>', methods=['GET', 'POST'])
@csrf.exempt
def mock_gateway(authority):
    if current_app.config.get('PAYMENT_GATEWAY') != 'mock':
        abort(404)
    s = MockGateway.sessions.get(authority) or abort(404)
    if request.method == 'POST':
        s['state'] = 'paid' if request.form.get('result') == 'pay' else 'cancelled'
        status = 'OK' if s['state'] == 'paid' else 'NOK'
        return redirect(url_for('payment.callback', Authority=authority, Status=status))
    return render_template('payment/mock.html', authority=authority, amount=s['amount'])
