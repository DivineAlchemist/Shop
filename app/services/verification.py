"""SMS verification codes: expiry, resend cooldown, hourly send cap and attempt limit."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import update, func

from ..extensions import db
from ..models import VerificationCode
from .sms import send_sms

TEMPLATE_BY_PURPOSE = {'register': 'verify_code', 'reset': 'reset_code'}


def _hash(phone, purpose, code):
    key = current_app.config['SECRET_KEY'].encode()
    return hmac.new(key, f'{phone}:{purpose}:{code}'.encode(), hashlib.sha256).hexdigest()


def issue_code(phone, purpose, user_id=None):
    """Create + send a code. Returns (ok, error_message)."""
    cfg = current_app.config
    now = datetime.utcnow()
    last = (VerificationCode.query.filter_by(phone=phone, purpose=purpose)
            .order_by(VerificationCode.id.desc()).first())
    cooldown = cfg['OTP_RESEND_COOLDOWN']
    if last and (now - last.created_at).total_seconds() < cooldown:
        wait = int(cooldown - (now - last.created_at).total_seconds()) + 1
        return False, f'Please wait {wait} seconds before requesting another code.'
    recent = VerificationCode.query.filter(
        VerificationCode.phone == phone, VerificationCode.created_at > now - timedelta(hours=1)).count()
    if recent >= cfg['OTP_MAX_SENDS_PER_HOUR']:
        return False, 'Too many codes requested. Try again later.'
    # invalidate older unconsumed codes
    db.session.execute(update(VerificationCode).where(
        VerificationCode.phone == phone, VerificationCode.purpose == purpose,
        VerificationCode.consumed_at.is_(None)).values(consumed_at=now))
    code = f'{secrets.randbelow(10**6):06d}'
    vc = VerificationCode(phone=phone, purpose=purpose, code_hash=_hash(phone, purpose, code),
                          created_at=now, expires_at=now + timedelta(seconds=cfg['OTP_TTL_SECONDS']))
    db.session.add(vc)
    db.session.commit()
    entry = send_sms(phone, TEMPLATE_BY_PURPOSE[purpose], purpose=purpose, redact=True, user_id=user_id,
                     code=code, minutes=max(1, cfg['OTP_TTL_SECONDS'] // 60))
    if entry is None or entry.status != 'sent':
        vc.consumed_at = datetime.utcnow()  # unusable code
        db.session.commit()
        return False, 'We could not send the SMS right now. Please try again shortly.'
    return True, None


def check_code(phone, purpose, code):
    """Validate and consume a code. Returns (ok, error_message)."""
    cfg = current_app.config
    now = datetime.utcnow()
    vc = (VerificationCode.query.filter_by(phone=phone, purpose=purpose, consumed_at=None)
          .order_by(VerificationCode.id.desc()).first())
    if vc is None or vc.expires_at < now:
        return False, 'The code is invalid or has expired. Request a new one.'
    if vc.attempts >= cfg['OTP_MAX_ATTEMPTS']:
        return False, 'Too many wrong attempts. Request a new code.'
    code = (code or '').strip()
    if not hmac.compare_digest(vc.code_hash, _hash(phone, purpose, code)):
        db.session.execute(update(VerificationCode).where(VerificationCode.id == vc.id)
                           .values(attempts=VerificationCode.attempts + 1))
        db.session.commit()
        return False, 'Incorrect code.'
    res = db.session.execute(update(VerificationCode).where(
        VerificationCode.id == vc.id, VerificationCode.consumed_at.is_(None)).values(consumed_at=now))
    db.session.commit()
    if res.rowcount != 1:  # consumed concurrently
        return False, 'The code is invalid or has expired. Request a new one.'
    return True, None
