"""Date helpers for payment schedules.

``add_months`` is implemented without external dependencies to keep the
behaviour explicit for the 29th, 30th and 31st.
"""
import calendar
import datetime as dt


def add_months(date: dt.date, months: int) -> dt.date:
    """Add months keeping the day; clamp to the last day of a shorter month.

    Example: 2026-01-31 + 1 month -> 2026-02-28 (or 02-29 on a leap year).
    """
    total = date.month - 1 + months
    year = date.year + total // 12
    month = total % 12 + 1
    day = min(date.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def add_days(date: dt.date, days: int) -> dt.date:
    return date + dt.timedelta(days=days)


def today_local() -> dt.date:
    """Today's date in the configured time zone (America/Mexico_City)."""
    from django.utils import timezone

    return timezone.localdate()


def now_local():
    from django.utils import timezone

    return timezone.localtime()
