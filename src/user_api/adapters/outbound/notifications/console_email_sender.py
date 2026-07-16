import logging

from user_api.domain.ports import EmailSender

logger = logging.getLogger(__name__)


class ConsoleEmailSender(EmailSender):
    """EmailSender Port implementation for v1 (ADR-003): logs the confirmation
    link instead of sending real email. No production email provider is
    configured yet — do not deploy to public production until a real adapter
    (SMTP/SES/SendGrid) exists behind this same Port."""

    async def send_verification_email(self, to: str, token: str) -> None:
        # debug (not info) + masked: this stand-in adapter must never persist
        # the full plaintext confirmation secret in application logs, even
        # in dev. Masking still lets a developer eyeball which token fired.
        masked = f"{token[:8]}..." if len(token) > 8 else "***"
        logger.debug("Verification email for %s — token=%s", to, masked)
