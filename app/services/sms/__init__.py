"""Reusable SMS service: provider abstraction, templates, idempotent logging, safe retries.

`send_sms` never raises: SMS problems must not break orders or authentication flows.
"""
import logging
import time
from datetime import datetime
from flask import current_app
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import SmsLog, StoreSettings
from .base import SMSProvider, SendResult
from .mock import MockProvider
from .templates import render

log = logging.getLogger(__name__)
_PROVIDERS = {}


def register_provider(name, factory):
    _PROVIDERS[name] = factory


def _kavenegar_factory(app):
    from .kavenegar import KavenegarProvider
    return KavenegarProvider(app.config['KAVENEGAR_API_KEY'], app.config['KAVENEGAR_SENDER'])


register_provider('mock', lambda app: MockProvider())
register_provider('kavenegar', _kavenegar_factory)


def get_provider():
    app = current_app._get_current_object()
    cached = app.extensions.get('sms_provider')
    if cached is None:
        name = app.config.get('SMS_PROVIDER', 'mock')
        if name not in _PROVIDERS:
            raise RuntimeError(f'Unknown SMS provider "{name}"')
        cached = app.extensions['sms_provider'] = _PROVIDERS[name](app)
    return cached


def _locale():
    s = StoreSettings.query.first()
    return (s.locale if s else 'en') or 'en'


def store_name():
    s = StoreSettings.query.first()
    return s.store_name if s else 'Shop'


def _deliver(provider, phone, body):
    """Send with bounded retries for transient failures."""
    retries = max(1, int(current_app.config.get('SMS_MAX_RETRIES', 3)))
    backoff = float(current_app.config.get('SMS_RETRY_BACKOFF', 0.5))
    attempts, result = 0, SendResult(ok=False, error='not attempted')
    for n in range(retries):
        attempts += 1
        try:
            result = provider.send(phone, body)
        except Exception as e:  # provider bug/misconfiguration must not propagate
            log.exception('SMS provider crashed')
            result = SendResult(ok=False, error=f'provider error: {type(e).__name__}', retryable=False)
        if result.ok or not result.retryable:
            break
        if n < retries - 1 and backoff:
            time.sleep(backoff * (2 ** n))
    return result, attempts


def send_sms(phone, template, *, purpose, dedupe_key=None, user_id=None, order_id=None,
             redact=False, **tokens):
    """Render + send + log. With `dedupe_key`, a message is only ever created once (retries of the
    same business operation return the existing log instead of sending again)."""
    try:
        if dedupe_key:
            existing = SmsLog.query.filter_by(dedupe_key=dedupe_key).first()
            if existing:
                return existing
        tokens.setdefault('store', store_name())
        if order_id is not None:
            tokens.setdefault('order_id', order_id)
        body = render(template, _locale(), **tokens)
        entry = SmsLog(dedupe_key=dedupe_key, phone=phone, purpose=purpose, template=template,
                       body='[redacted]' if redact else body, status='queued',
                       user_id=user_id, order_id=order_id)
        db.session.add(entry)
        try:
            db.session.commit()  # claim the dedupe key before sending
        except IntegrityError:
            db.session.rollback()
            return SmsLog.query.filter_by(dedupe_key=dedupe_key).first()
        provider = get_provider()
        result, attempts = _deliver(provider, phone, body)
        entry.attempts = attempts
        entry.provider = provider.name
        if result.ok:
            entry.status, entry.provider_message_id = 'sent', result.message_id
            entry.sent_at = datetime.utcnow()
        else:
            entry.status, entry.error = 'failed', (result.error or 'unknown error')[:300]
            log.warning('SMS to %s failed (%s): %s', phone[-4:], purpose, entry.error)
        db.session.commit()
        return entry
    except Exception:
        db.session.rollback()
        log.exception('send_sms failed unexpectedly')
        return None


def retry_failed(limit=50, max_attempts=6):
    """Re-send failed, non-sensitive messages (used by `flask sms-retry`). Returns number recovered."""
    rows = (SmsLog.query.filter(SmsLog.status == 'failed', SmsLog.attempts < max_attempts,
                                SmsLog.body != '[redacted]')
            .order_by(SmsLog.id).limit(limit).all())
    ok = 0
    for r in rows:
        result, attempts = _deliver(get_provider(), r.phone, r.body)
        r.attempts += attempts
        if result.ok:
            r.status, r.provider_message_id, r.sent_at, r.error = 'sent', result.message_id, datetime.utcnow(), None
            ok += 1
        else:
            r.error = (result.error or '')[:300]
        db.session.commit()
    return ok
