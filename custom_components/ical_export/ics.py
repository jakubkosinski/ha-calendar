"""Minimal RFC 5545 serializer. Has no Home Assistant dependencies."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

PRODID = "-//ical_export//Home Assistant//EN"


@dataclass(frozen=True)
class IcsEvent:
    """Plain event representation decoupled from HA's CalendarEvent."""

    start: date | datetime
    end: date | datetime
    summary: str
    uid: str | None = None
    recurrence_id: str | None = None
    description: str | None = None
    location: str | None = None
    source: str = ""


def escape_text(value: str) -> str:
    """Escape a TEXT value."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold(line: str) -> str:
    """Fold a content line to at most 75 octets, never splitting UTF-8 chars."""
    if len(line.encode()) <= 75:
        return line
    parts: list[str] = []
    current = ""
    limit = 75
    for char in line:
        if len((current + char).encode()) > limit:
            parts.append(current)
            current = char
            limit = 74  # continuation lines start with a space
        else:
            current += char
    parts.append(current)
    return "\r\n ".join(parts)


def _format_dt(value: date | datetime) -> tuple[str, str]:
    """Return (parameter suffix, formatted value)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return "", value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ";VALUE=DATE", value.strftime("%Y%m%d")


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)


def make_uid(event: IcsEvent) -> str:
    """Stable UID; instances of recurring events get a distinct suffix.

    UIDs come from third-party calendars and are written unescaped, so one holding
    control characters (e.g. CRLF) is replaced by a hash to prevent injecting lines.
    """
    if event.uid:
        base = event.uid
        if event.recurrence_id:
            base = f"{base}_{event.recurrence_id}"
        if _has_control_chars(base):
            base = hashlib.sha256(base.encode()).hexdigest()[:32]
        return f"{base}@ical_export"
    start = _format_dt(event.start)[1]
    digest = hashlib.sha256(f"{event.source}|{event.summary}|{start}".encode()).hexdigest()[:32]
    return f"{digest}@ical_export"


def build_calendar(
    name: str,
    events: Iterable[IcsEvent],
    refresh_minutes: int = 15,
    now: datetime | None = None,
) -> str:
    """Build a VCALENDAR document."""
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(name)}",
        f"REFRESH-INTERVAL;VALUE=DURATION:PT{refresh_minutes}M",
        f"X-PUBLISHED-TTL:PT{refresh_minutes}M",
    ]
    for event in events:
        start_param, start_val = _format_dt(event.start)
        end_param, end_val = _format_dt(event.end)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{make_uid(event)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART{start_param}:{start_val}",
            f"DTEND{end_param}:{end_val}",
            f"SUMMARY:{escape_text(event.summary or '')}",
        ]
        if event.description:
            lines.append(f"DESCRIPTION:{escape_text(event.description)}")
        if event.location:
            lines.append(f"LOCATION:{escape_text(event.location)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
