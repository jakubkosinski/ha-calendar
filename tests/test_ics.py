"""Tests for the RFC 5545 serializer."""

from datetime import UTC, date, datetime, timedelta, timezone

from icalendar import Calendar

from custom_components.ical_export.ics import (
    IcsEvent,
    build_calendar,
    escape_text,
    fold,
    make_uid,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_escape():
    assert escape_text("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"


def test_fold_respects_utf8_and_length():
    line = "SUMMARY:" + "zażółć gęślą jaźń " * 10
    folded = fold(line)
    for part in folded.split("\r\n"):
        assert len(part.encode()) <= 75
    assert folded.replace("\r\n ", "") == line


def test_all_day_and_timed_events_parse():
    tz = timezone(timedelta(hours=2))
    events = [
        IcsEvent(date(2026, 3, 1), date(2026, 3, 2), "Holiday, fun", uid="a"),
        IcsEvent(
            datetime(2026, 3, 1, 12, 0, tzinfo=tz),
            datetime(2026, 3, 1, 13, 0, tzinfo=tz),
            "Meeting",
            description="Line1\nLine2",
            location="Room; 1",
            source="calendar.x",
        ),
    ]
    text = build_calendar("Test", events, 15, now=NOW)
    assert "DTSTART;VALUE=DATE:20260301" in text
    assert "DTSTART:20260301T100000Z" in text
    parsed = Calendar.from_ical(text)
    items = list(parsed.walk("VEVENT"))
    assert len(items) == 2
    assert str(items[0]["SUMMARY"]) == "Holiday, fun"
    assert str(items[1]["DESCRIPTION"]) == "Line1\nLine2"
    assert str(parsed["X-WR-CALNAME"]) == "Test"


def test_uid_stable_and_recurrence_distinct():
    a = IcsEvent(NOW, NOW, "x", source="calendar.x")
    assert make_uid(a) == make_uid(a)
    r1 = IcsEvent(NOW, NOW, "x", uid="u", recurrence_id="1")
    r2 = IcsEvent(NOW, NOW, "x", uid="u", recurrence_id="2")
    assert make_uid(r1) != make_uid(r2)


def test_uid_with_control_chars_cannot_inject_lines():
    evil = IcsEvent(
        start=NOW,
        end=NOW,
        summary="x",
        uid="abc\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nEND:VALARM",
        recurrence_id="20260101\nX-EVIL:1",
    )
    uid = make_uid(evil)
    assert "\r" not in uid and "\n" not in uid

    body = build_calendar("t", [evil], now=NOW)
    event = next(c for c in Calendar.from_ical(body).walk("VEVENT"))
    assert not list(event.walk("VALARM"))
    assert "X-EVIL" not in event
    assert "X-EVIL" not in body.replace("\r\n", "")
