"""Order/marketing SMS built on the SMS service. All functions are failure-safe and idempotent."""
import logging
from itsdangerous import URLSafeSerializer, BadSignature
from flask import current_app, url_for
from datetime import datetime

from ..extensions import db
from ..models import User, StoreSettings
from .sms import send_sms

log = logging.getLogger(__name__)


def money_text(amount):
    s = StoreSettings.query.first()
    cur = s.currency if s else ''
    return f'{amount:,.2f} {cur}'.strip() if cur not in ('IRT', 'IRR') else f'{int(amount):,} {cur}'


def _order_phone(order):
    return order.ship_phone or order.user.phone


def notify_order_placed(order):
    return send_sms(order.user.phone, 'order_confirmed', purpose='order', order_id=order.id,
                    user_id=order.user_id, dedupe_key=f'order:{order.id}:confirmed',
                    total=money_text(order.total_amount))


_STATUS_TEMPLATES = {'preparing': 'order_preparing', 'shipped': 'order_shipped',
                     'received': 'order_received', 'cancelled': 'order_cancelled'}


def notify_status(order, status):
    key = _STATUS_TEMPLATES.get(status)
    if not key:
        return None
    # one message per (order, status) - repeated transitions/retries never double-send
    return send_sms(order.user.phone, key, purpose='order', order_id=order.id, user_id=order.user_id,
                    dedupe_key=f'order:{order.id}:{status}', tracking=order.tracking_code or '',
                    provider=order.shipment_provider or '')


# ------------------------------------------------------------ marketing consent
def _serializer():
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='sms-optout')


def optout_token(user):
    return _serializer().dumps(user.id)


def apply_optout(token):
    try:
        uid = _serializer().loads(token)
    except BadSignature:
        return False
    user = db.session.get(User, uid)
    if not user:
        return False
    set_marketing_consent(user, False)
    return True


def set_marketing_consent(user, consent):
    if consent and not user.sms_marketing_consent:
        user.sms_marketing_consent, user.marketing_consent_at, user.marketing_opt_out_at = True, datetime.utcnow(), None
    elif not consent and user.sms_marketing_consent:
        user.sms_marketing_consent, user.marketing_opt_out_at = False, datetime.utcnow()
    db.session.commit()


def send_marketing(message, campaign_id, limit=500):
    """Send `message` only to verified, consenting users. Idempotent per (campaign, user)."""
    sent = 0
    users = (User.query.filter_by(sms_marketing_consent=True, phone_verified=True, is_active_account=True)
             .order_by(User.id).limit(limit).all())
    from ..models import SmsLog
    for u in users:
        if SmsLog.query.filter_by(dedupe_key=f'marketing:{campaign_id}:{u.id}').first():
            continue  # already handled for this campaign
        entry = send_sms(u.phone, 'marketing', purpose='marketing', user_id=u.id,
                         dedupe_key=f'marketing:{campaign_id}:{u.id}', message=message,
                         optout_url=url_for('customer.sms_optout', token=optout_token(u), _external=True))
        if entry is not None and entry.status == 'sent':
            sent += 1
    return sent
