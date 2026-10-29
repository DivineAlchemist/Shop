import logging
from .base import SMSProvider, SendResult

log = logging.getLogger(__name__)


class MockProvider(SMSProvider):
    """Records messages in memory (tests/dev). Never touches the network."""
    name = 'mock'
    outbox = []          # list of (phone, text)
    fail_next = []       # queue of SendResult to return instead of success (tests)

    def send(self, phone, text):
        if MockProvider.fail_next:
            return MockProvider.fail_next.pop(0)
        MockProvider.outbox.append((phone, text))
        log.info('[mock-sms] to=%s text=%s', phone, text)
        return SendResult(ok=True, message_id=f'mock-{len(MockProvider.outbox)}')

    @classmethod
    def reset(cls):
        cls.outbox.clear()
        cls.fail_next.clear()
