from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_DEFAULT_TZ = "Asia/Manila"
_tz = ZoneInfo(_DEFAULT_TZ)


def configure(tz_name: str | None) -> None:
    """sets the timezone"""
    global _tz
    _tz = ZoneInfo(tz_name or _DEFAULT_TZ)


def tz() -> ZoneInfo:
    return _tz


def now() -> datetime:
    return datetime.now(_tz)


def combine(day: date, at: time) -> datetime:
    """date + time from the form into a datetime"""
    return datetime.combine(day, at, tzinfo=_tz)


_FRACTION = re.compile(r"\.(\d+)")


def parse(value: str | datetime | None) -> datetime | None:
    """reads a timestamp from the databse"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.strip().replace(" ", "T", 1)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        text = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz)
    return dt.astimezone(_tz)


def to_iso(dt: datetime) -> str:
    return dt.isoformat()


# formatting for display (no %-d becuase it breaks on windows)

def fmt_date(dt: datetime) -> str:
    dt = dt.astimezone(_tz)
    return f"{dt:%a}, {dt:%b} {dt.day}, {dt.year}"


def fmt_time(dt: datetime) -> str:
    dt = dt.astimezone(_tz)
    return f"{dt.hour % 12 or 12}:{dt:%M} {dt:%p}"


def fmt_range(start: datetime, end: datetime) -> str:
    return f"{fmt_date(start)} · {fmt_time(start)} – {fmt_time(end)}"
