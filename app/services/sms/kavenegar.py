"""Kavenegar REST adapter.

API (https://kavenegar.com/rest.html): POST https://api.kavenegar.com/v1/{API-KEY}/sms/send.json
with form fields receptor, message, sender. Response JSON: {"return": {"status": 200, "message": ...},
"entries": [{"messageid": ..., ...}]} - status 200 means accepted. The API key is part of the URL
path, so it is masked in every log/error message.
"""
import logging
import requests
from flask import current_app
from .base import SMSProvider, SendResult

log = logging.getLogger(__name__)
BASE_URL = 'https://api.kavenegar.com/v1/{key}/{action}/{method}.json'
# Provider-side conditions that are worth retrying (service unreachable / throttled / temporarily disabled).
RETRYABLE_STATUS = {409, 451, 501}


class KavenegarProvider(SMSProvider):
    name = 'kavenegar'

    def __init__(self, api_key, sender, timeout=10):
        if current_app.config.get('TESTING'):
            raise RuntimeError('Real SMS provider is disabled when TESTING')
        if not api_key:
            raise RuntimeError('KAVENEGAR_API_KEY is not configured')
        self.api_key, self.sender, self.timeout = api_key, sender, timeout

    def _mask(self, text):
        return str(text).replace(self.api_key, '***')

    def _post(self, action, method, data):
        url = BASE_URL.format(key=self.api_key, action=action, method=method)
        try:
            resp = requests.post(url, data=data, timeout=self.timeout,
                                 headers={'Accept': 'application/json'})
        except requests.RequestException as e:
            return SendResult(ok=False, error=self._mask(f'network error: {e}'), retryable=True)
        try:
            body = resp.json()
            ret = body['return']
            status = int(ret['status'])
        except (ValueError, KeyError, TypeError):
            return SendResult(ok=False, error=f'unexpected response (HTTP {resp.status_code})',
                              retryable=resp.status_code >= 500)
        if status == 200:
            entries = body.get('entries')
            entry = entries[0] if isinstance(entries, list) and entries else (entries or {})
            return SendResult(ok=True, message_id=str(entry.get('messageid', '')) or None)
        return SendResult(ok=False, error=self._mask(f'kavenegar {status}: {ret.get("message", "")}'),
                          retryable=status in RETRYABLE_STATUS or resp.status_code >= 500)

    def send(self, phone, text):
        data = {'receptor': phone, 'message': text}
        if self.sender:
            data['sender'] = self.sender
        return self._post('sms', 'send', data)
