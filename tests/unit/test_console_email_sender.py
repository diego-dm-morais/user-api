import logging

import pytest

from user_api.adapters.outbound.notifications.console_email_sender import ConsoleEmailSender

FULL_TOKEN = "a-very-secret-high-entropy-confirmation-token-value"


async def test_send_verification_email_never_logs_full_token_at_info_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Security regression: the confirmation token must never appear
    verbatim in application logs, and must not be emitted at INFO (only
    DEBUG, for local dev troubleshooting)."""
    sender = ConsoleEmailSender()

    with caplog.at_level(logging.DEBUG):
        await sender.send_verification_email("ada@example.com", FULL_TOKEN)

    info_records = [r for r in caplog.records if r.levelno >= logging.INFO]
    assert info_records == []

    full_log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert FULL_TOKEN not in full_log_text
    assert FULL_TOKEN[:8] in full_log_text  # still useful for dev troubleshooting
