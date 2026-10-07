"""HTTP views serving iCal feeds."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import timedelta

from aiohttp import web
from homeassistant.components.calendar import DATA_COMPONENT, CalendarEntity
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_TTL_SECONDS,
    CONF_CALENDARS,
    CONF_FUTURE_DAYS,
    CONF_NAME,
    CONF_PAST_DAYS,
    CONF_TOKEN,
    DEFAULT_FUTURE_DAYS,
    DEFAULT_PAST_DAYS,
    DOMAIN,
    REFRESH_MINUTES,
)
from .ics import IcsEvent, build_calendar

_LOGGER = logging.getLogger(__name__)

ALL_FEED = "all"


def _find_entry(hass: HomeAssistant, token: str) -> ConfigEntry | None:
    """Find the loaded entry matching token, in constant time per entry."""
    match = None
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if hmac.compare_digest(entry.data[CONF_TOKEN].encode(), token.encode()):
            match = entry
    return match


def _option(entry: ConfigEntry, key: str, default: int) -> int:
    return int(entry.options.get(key, default))


def _calendars(entry: ConfigEntry) -> list[str]:
    return entry.options.get(CONF_CALENDARS, entry.data.get(CONF_CALENDARS, []))


async def _fetch(hass: HomeAssistant, entry: ConfigEntry, entity_id: str) -> list[IcsEvent]:
    entity: CalendarEntity | None = hass.data[DATA_COMPONENT].get_entity(entity_id)
    if entity is None:
        _LOGGER.warning("Calendar %s not available", entity_id)
        return []
    now = dt_util.now()
    start = now - timedelta(days=_option(entry, CONF_PAST_DAYS, DEFAULT_PAST_DAYS))
    end = now + timedelta(days=_option(entry, CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS))
    try:
        events = await entity.async_get_events(hass, start, end)
    except Exception:  # noqa: BLE001 - one broken provider must not kill the feed
        _LOGGER.exception("Failed to fetch events from %s", entity_id)
        return []
    return [
        IcsEvent(
            start=e.start,
            end=e.end,
            summary=e.summary,
            uid=e.uid,
            recurrence_id=e.recurrence_id,
            description=e.description,
            location=e.location,
            source=entity_id,
        )
        for e in events
    ]


async def _render(hass: HomeAssistant, entry: ConfigEntry, feed: str) -> tuple[str, str] | None:
    """Return (body, etag) for a feed, or None if the feed doesn't exist."""
    calendars = _calendars(entry)
    if feed == ALL_FEED:
        entity_ids = calendars
        title = entry.data[CONF_NAME]
    else:
        entity_id = f"calendar.{feed}"
        if entity_id not in calendars:
            return None
        entity_ids = [entity_id]
        state = hass.states.get(entity_id)
        title = state.name if state else entity_id

    cache: dict = hass.data[DOMAIN]["cache"]
    key = (entry.entry_id, feed)
    cached = cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    results = await asyncio.gather(*(_fetch(hass, entry, e) for e in entity_ids))
    events = [event for chunk in results for event in chunk]
    body = build_calendar(title, events, REFRESH_MINUTES)
    etag = f'"{hashlib.sha256(_stable(body).encode()).hexdigest()[:32]}"'
    cache[key] = (time.monotonic(), body, etag)
    return body, etag


def _stable(body: str) -> str:
    """Drop DTSTAMP lines so the ETag only changes with real content."""
    return "\n".join(ln for ln in body.split("\r\n") if not ln.startswith("DTSTAMP"))


class ICalFeedView(HomeAssistantView):
    """Serve `.ics` feeds guarded by a secret token in the URL."""

    url = "/api/ical_export/{token}/{name}.ics"
    name = "api:ical_export:feed"
    requires_auth = False
    cors_allowed = False

    async def get(self, request: web.Request, token: str, name: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entry = _find_entry(hass, token)
        if entry is None:
            return web.Response(status=404)
        rendered = await _render(hass, entry, name)
        if rendered is None:
            return web.Response(status=404)
        body, etag = rendered
        headers = {
            "ETag": etag,
            "Cache-Control": f"private, max-age={CACHE_TTL_SECONDS}",
        }
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers=headers)
        headers["Content-Disposition"] = f'inline; filename="{name}.ics"'
        return web.Response(
            body=body.encode(),
            content_type="text/calendar",
            charset="utf-8",
            headers=headers,
        )
