"""Time helpers.

All datetimes in Queue&A are timezone-aware. They are stored in Supabase as
``timestamptz`` (UTC) and shown to users in the app's timezone, which defaults
to Asia/Manila and can be changed in ``.streamlit/secrets.toml``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_DEFAULT_TZ = "Asia/Manila"
_tz = ZoneInfo(_DEFAULT_TZ)


def configure(tz_name: str | None) -> None:
    """Set the timezone used for display and for interpreting form inputs."""
    global _tz
    _tz = ZoneInfo(tz_name or _DEFAULT_TZ)


def tz() -> ZoneInfo:
    return _tz


def now() -> datetime:
    return datetime.now(_tz)


def combine(day: date, at: time) -> datetime:
    """Turn a date + time picked in the UI into an aware datetime."""
    return datetime.combine(day, at, tzinfo=_tz)


_FRACTION = re.compile(r"\.(\d+)")


def parse(value: str | datetime | None) -> datetime | None:
    """Parse an ISO timestamp from the database into an aware local datetime.

    Handles a trailing ``Z`` and fractional seconds of any length, which older
    Python versions' ``fromisoformat`` cannot.
    """
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


# ---- display formatting (portable: no %-d, which fails on Windows) ----

def fmt_date(dt: datetime) -> str:
    dt = dt.astimezone(_tz)
    return f"{dt:%a}, {dt:%b} {dt.day}, {dt.year}"


def fmt_time(dt: datetime) -> str:
    dt = dt.astimezone(_tz)
    return f"{dt.hour % 12 or 12}:{dt:%M} {dt:%p}"


def fmt_range(start: datetime, end: datetime) -> str:
    return f"{fmt_date(start)} · {fmt_time(start)} – {fmt_time(end)}"
