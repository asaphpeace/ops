from datetime import datetime, timedelta

VALID_WINDOWS = ("week", "month", "quarter", "year")


def window_start(window: str) -> datetime:
    """Start of the requested reporting window, as of now.

    "week" and "quarter" are simple rolling windows (last 7 / last 90 days);
    "month" and "year" are calendar-to-date (matching the existing precedent
    in upgrades.py::pipeline_summary()'s done_this_month) — no fiscal-quarter
    complexity, nothing else in this app has one."""
    now = datetime.utcnow()
    if window == "week":
        return now - timedelta(days=7)
    if window == "quarter":
        return now - timedelta(days=90)
    if window == "year":
        return datetime(now.year, 1, 1)
    return datetime(now.year, now.month, 1)
