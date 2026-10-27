from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=32)
def zone(tz: str) -> ZoneInfo:
    return ZoneInfo(tz)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def local_display(value: str, tz: str) -> str:
    """Tenant-local display string, e.g. 2026-01-11 00:30."""
    return parse_utc(value).astimezone(zone(tz)).strftime("%Y-%m-%d %H:%M")


def local_date(value: str, tz: str) -> str:
    """Tenant-local calendar date, e.g. 2026-01-11 (A5)."""
    return parse_utc(value).astimezone(zone(tz)).strftime("%Y-%m-%d")
