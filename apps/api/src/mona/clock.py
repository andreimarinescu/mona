from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def now() -> datetime:
    """The one wall clock read by tools and cards; tests patch it."""
    return datetime.now(UTC)


def paris_today(at: datetime | None = None) -> date:
    return (at or now()).astimezone(PARIS).date()
