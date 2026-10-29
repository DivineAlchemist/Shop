from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentInit:
    ok: bool
    authority: Optional[str] = None
    redirect_url: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class PaymentVerify:
    ok: bool
    already_verified: bool = False
    ref_id: Optional[str] = None
    card_pan: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False  # network/transient failure: the payment may still be valid


class PaymentGateway:
    """Interface for payment gateways. Amounts are integers in the gateway's currency (Rials)."""
    name = 'base'
    currencies = ()  # store currencies this gateway can charge (empty = any)

    def request(self, amount, callback_url, description, mobile=None, order_id=None) -> PaymentInit:
        raise NotImplementedError

    def verify(self, authority, amount) -> PaymentVerify:
        raise NotImplementedError
