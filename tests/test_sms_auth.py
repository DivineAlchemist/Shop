from unittest import mock
import requests
from app.extensions import db
from app.models import User, SmsLog, VerificationCode
from app.services import verification, notifications
from app.services.sms import send_sms, retry_failed
from app.services.sms.base import SendResult
from app.services.sms.kavenegar import KavenegarProvider
from app.services.sms.mock import MockProvider
from .conftest import make_user, login


def last_code():
    import re
    return re.search(r'\b(\d{6})\b', MockProvider.outbox[-1][1]).group(1)


def test_registration_requires_sms_verification(app, client):
    r = client.post('/auth/register', data={'name': 'Sara', 'phone': '+98 912 345 6789', 'password': 'secret123',
                                            'confirm': 'secret123', 'marketing': 'y'})
    assert r.status_code == 302 and '/auth/verify' in r.headers['Location']
    u = User.query.one(); assert u.phone == '09123456789' and not u.phone_verified and u.sms_marketing_consent
    assert login(client, u, 'secret123').headers['Location'].endswith('/auth/verify')   # cannot log in yet
    assert client.post('/auth/verify', data={'code': '000000'}).status_code == 200
    client.post('/auth/verify', data={'code': last_code()})
    db.session.refresh(u); assert u.phone_verified
    assert login(client, u, 'secret123').status_code == 302
    assert {l.body for l in SmsLog.query.filter_by(purpose='register')} == {'[redacted]'}        # codes are never stored


def test_code_attempt_limit_expiry_and_resend_limit(app):
    phone = '09123456789'
    ok, err = verification.issue_code(phone, 'register'); assert ok
    code = last_code()
    for _ in range(app.config['OTP_MAX_ATTEMPTS']):
        assert not verification.check_code(phone, 'register', '999999' if code != '999999' else '111111')[0]
    assert 'Too many' in verification.check_code(phone, 'register', code)[1]            # locked even with right code
    verification.issue_code(phone, 'register'); code = last_code()
    vc = VerificationCode.query.filter_by(consumed_at=None).one()
    from datetime import datetime, timedelta
    vc.expires_at = datetime.utcnow() - timedelta(seconds=1); db.session.commit()
    assert not verification.check_code(phone, 'register', code)[0]                      # expired
    app.config['OTP_MAX_SENDS_PER_HOUR'] = 3
    results = [verification.issue_code(phone, 'register')[0] for _ in range(3)]
    assert results.count(False) >= 1                                                    # hourly cap


def test_resend_cooldown(app):
    app.config['OTP_RESEND_COOLDOWN'] = 60
    assert verification.issue_code('09123456780', 'register')[0]
    ok, err = verification.issue_code('09123456780', 'register')
    assert not ok and 'wait' in err


def test_code_single_use_and_send_failure(app):
    assert verification.issue_code('09123456781', 'reset')[0]
    code = last_code()
    assert verification.check_code('09123456781', 'reset', code)[0]
    assert not verification.check_code('09123456781', 'reset', code)[0]                 # consumed
    MockProvider.fail_next.append(SendResult(ok=False, error='down'))
    ok, err = verification.issue_code('09123456782', 'reset')
    assert not ok and VerificationCode.query.filter_by(phone='09123456782', consumed_at=None).count() == 0


def test_password_recovery_flow_no_enumeration(app, client):
    u = make_user('09123456783', password='oldpass12')
    r1 = client.post('/auth/forgot', data={'phone': '09123456783'}); r2 = client.post('/auth/forgot', data={'phone': '09999999999'})
    assert r1.status_code == r2.status_code == 302 and r1.headers['Location'] == r2.headers['Location']
    assert len(MockProvider.outbox) == 1                                                # only the real account got an SMS
    client.post('/auth/forgot', data={'phone': '09123456783'})
    r = client.post('/auth/reset', data={'code': last_code(), 'password': 'newpass123', 'confirm': 'newpass123'})
    assert r.status_code == 302
    assert login(client, u, 'newpass123').status_code == 302


def test_login_lockout_and_safe_redirect(app, client):
    u = make_user('09123456784')
    for _ in range(app.config['LOGIN_MAX_FAILURES']):
        client.post('/auth/login', data={'phone': u.phone, 'password': 'wrong'})
    r = client.post('/auth/login', data={'phone': u.phone, 'password': 'password1'})
    assert r.status_code == 200                                                         # locked
    db.session.refresh(u); u.locked_until = None; db.session.commit()
    r = client.post('/auth/login?next=https://evil.example', data={'phone': u.phone, 'password': 'password1'})
    assert r.headers['Location'].endswith('/')                                          # open redirect blocked


def test_sms_idempotency_failure_isolation_and_retry(app):
    a = send_sms('09120000001', 'order_cancelled', purpose='order', dedupe_key='k1', order_id=5)
    b = send_sms('09120000001', 'order_cancelled', purpose='order', dedupe_key='k1', order_id=5)
    assert a.id == b.id and len(MockProvider.outbox) == 1
    MockProvider.fail_next += [SendResult(ok=False, error='timeout', retryable=True)] * 3
    f = send_sms('09120000001', 'order_cancelled', purpose='order', dedupe_key='k2', order_id=6)
    assert f.status == 'failed' and f.attempts == 3
    assert send_sms('09120000001', 'order_cancelled', purpose='order', dedupe_key='k2').id == f.id   # no duplicate
    assert retry_failed() == 1 and SmsLog.query.filter_by(dedupe_key='k2').one().status == 'sent'
    with mock.patch('app.services.sms.get_provider', side_effect=RuntimeError('misconfigured')):
        assert send_sms('09120000001', 'order_cancelled', purpose='order', dedupe_key='k3') is None  # never raises


def test_marketing_consent_and_optout(app, client):
    yes = make_user('09120000011'); no = make_user('09120000012')
    notifications.set_marketing_consent(yes, True)
    with app.test_request_context():
        assert notifications.send_marketing('Sale!', 'c1') == 1
        assert notifications.send_marketing('Sale!', 'c1') == 0                          # idempotent per campaign
        token = notifications.optout_token(yes)
    assert 'Opt out' in MockProvider.outbox[-1][1] and MockProvider.outbox[-1][0] == yes.phone
    assert client.post(f'/sms/optout/{token}').status_code == 200
    db.session.refresh(yes); assert not yes.sms_marketing_consent and yes.marketing_opt_out_at
    assert 'not valid' in client.post('/sms/optout/garbage').get_data(as_text=True)


def test_kavenegar_adapter_with_mocked_http(app):
    app.config['TESTING'] = False
    p = KavenegarProvider('KEY123', '10004346')
    ok = mock.Mock(status_code=200, json=lambda: {'return': {'status': 200, 'message': 'ok'}, 'entries': [{'messageid': 8085}]})
    with mock.patch('requests.post', return_value=ok) as post:
        r = p.send('09123456789', 'hi')
    assert post.call_args[0][0] == 'https://api.kavenegar.com/v1/KEY123/sms/send.json'
    assert post.call_args[1]['data'] == {'receptor': '09123456789', 'message': 'hi', 'sender': '10004346'}
    assert r.ok and r.message_id == '8085'
    bad = mock.Mock(status_code=200, json=lambda: {'return': {'status': 418, 'message': 'credit KEY123'}})
    with mock.patch('requests.post', return_value=bad):
        r = p.send('0912', 'x')
    assert not r.ok and not r.retryable and 'KEY123' not in r.error                        # key never leaks
    with mock.patch('requests.post', side_effect=requests.Timeout('KEY123 slow')):
        r = p.send('0912', 'x')
    assert not r.ok and r.retryable and 'KEY123' not in r.error
    app.config['TESTING'] = True
    import pytest
    with pytest.raises(RuntimeError):
        KavenegarProvider('k', 's')
