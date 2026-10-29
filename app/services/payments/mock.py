"""Mock gateway for development/tests: a local page lets you 'pay' or 'cancel'. Never contacts a bank."""
import uuid
from flask import url_for
from .base import PaymentGateway, PaymentInit, PaymentVerify


class MockGateway(PaymentGateway):
    name = 'mock'
    currencies = ()
    sessions = {}   # authority -> {'amount': int, 'state': 'pending'|'paid'|'cancelled', 'verified': bool}
    fail_verify_network = False

    def request(self, amount, callback_url, description, mobile=None, order_id=None):
        authority = 'MOCK' + uuid.uuid4().hex[:28]
        MockGateway.sessions[authority] = {'amount': int(amount), 'state': 'pending', 'verified': False,
                                           'callback_url': callback_url}
        return PaymentInit(ok=True, authority=authority,
                           redirect_url=url_for('payment.mock_gateway', authority=authority))

    def verify(self, authority, amount):
        if MockGateway.fail_verify_network:
            return PaymentVerify(ok=False, retryable=True, error_code='network', error_message='unreachable')
        s = MockGateway.sessions.get(authority)
        if not s or s['state'] != 'paid':
            return PaymentVerify(ok=False, error_code='-51', error_message='Payment not completed')
        if s['amount'] != int(amount):
            return PaymentVerify(ok=False, error_code='-50', error_message='Amount mismatch')
        already, s['verified'] = s['verified'], True
        return PaymentVerify(ok=True, already_verified=already, ref_id=f'REF{authority[-8:]}', card_pan='603799******1234')

    @classmethod
    def reset(cls):
        cls.sessions.clear()
        cls.fail_verify_network = False
