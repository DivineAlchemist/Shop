"""Zarinpal v4 REST gateway (https://www.zarinpal.com/docs/paymentGateway/connectToGateway).

request : POST {api}/pg/v4/payment/request.json  {merchant_id, amount(Rial), callback_url, description, metadata}
          -> {"data": {"code": 100, "authority": "A000..."}, "errors": []}
redirect: {pay}/pg/StartPay/{authority}
callback: GET callback_url?Authority=...&Status=OK|NOK
verify  : POST {api}/pg/v4/payment/verify.json {merchant_id, amount, authority}
          -> data.code 100 = verified now, 101 = already verified earlier (both mean paid).
"""
import logging
import requests
from flask import current_app
from .base import PaymentGateway, PaymentInit, PaymentVerify

log = logging.getLogger(__name__)
LIVE = ('https://payment.zarinpal.com', 'https://payment.zarinpal.com')
SANDBOX = ('https://sandbox.zarinpal.com', 'https://sandbox.zarinpal.com')


class ZarinpalGateway(PaymentGateway):
    name = 'zarinpal'
    currencies = ('IRR', 'IRT')

    def __init__(self, merchant_id, sandbox=False, timeout=15):
        if current_app.config.get('TESTING'):
            raise RuntimeError('Real payment gateway is disabled when TESTING')
        if not merchant_id:
            raise RuntimeError('ZARINPAL_MERCHANT_ID is not configured')
        self.merchant_id, self.timeout = merchant_id, timeout
        self.api, self.pay = SANDBOX if sandbox else LIVE

    def _post(self, path, payload):
        try:
            r = requests.post(f'{self.api}/pg/v4/payment/{path}.json', json=payload, timeout=self.timeout,
                              headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
            return r.status_code, r.json()
        except requests.RequestException as e:
            log.warning('Zarinpal network error: %s', type(e).__name__)
            return None, None
        except ValueError:
            return None, None

    @staticmethod
    def _error(body):
        errs = (body or {}).get('errors')
        if isinstance(errs, dict):
            return str(errs.get('code', '')), str(errs.get('message', ''))
        if isinstance(errs, list) and errs:
            return str(errs[0].get('code', '')), str(errs[0].get('message', ''))
        return '', ''

    def request(self, amount, callback_url, description, mobile=None, order_id=None):
        payload = {'merchant_id': self.merchant_id, 'amount': int(amount), 'callback_url': callback_url,
                   'description': description[:200]}
        if mobile:
            payload['metadata'] = {'mobile': mobile}
        status, body = self._post('request', payload)
        if body is None:
            return PaymentInit(ok=False, error_code='network', error_message='Payment gateway unreachable.')
        data = body.get('data') or {}
        if isinstance(data, dict) and data.get('code') == 100 and data.get('authority'):
            return PaymentInit(ok=True, authority=data['authority'],
                               redirect_url=f"{self.pay}/pg/StartPay/{data['authority']}")
        code, msg = self._error(body)
        return PaymentInit(ok=False, error_code=code or str(data.get('code', '')), error_message=msg or 'Gateway rejected the request.')

    def verify(self, authority, amount):
        status, body = self._post('verify', {'merchant_id': self.merchant_id, 'amount': int(amount),
                                             'authority': authority})
        if body is None:
            return PaymentVerify(ok=False, retryable=True, error_code='network',
                                 error_message='Could not reach the gateway to verify the payment.')
        data = body.get('data') or {}
        code = data.get('code') if isinstance(data, dict) else None
        if code in (100, 101):
            return PaymentVerify(ok=True, already_verified=(code == 101),
                                 ref_id=str(data.get('ref_id', '')) or None, card_pan=data.get('card_pan'))
        ecode, emsg = self._error(body)
        return PaymentVerify(ok=False, error_code=ecode or str(code), error_message=emsg or 'Payment was not verified.',
                             retryable=bool(status and status >= 500))
