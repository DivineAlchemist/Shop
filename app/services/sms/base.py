from dataclasses import dataclass
from typing import Optional


@dataclass
class SendResult:
    ok: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False


class SMSProvider:
    """Interface every SMS backend implements (add new providers by subclassing + registering)."""
    name = 'base'

    def send(self, phone: str, text: str) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError
