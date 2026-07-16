from datetime import UTC, datetime

from user_api.domain.ports import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
