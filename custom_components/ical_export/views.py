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

from .calendars import CONF_REF, CONF_SLUG, entity_ids, get_calendars, resolve_entity_id
from .const import (
    CACHE_TTL_SECONDS,
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
from .runtime import ICalConfigEntry

_LOGGER = logging.getLogger(__name__)

ALL_FEED = "all"
RETRY_AFTER_SECONDS = 60


class FeedUnavailableError(Exception):
    """A calendar could not be read and there is no earlier copy to serve."""


def _find_entry(hass: HomeAssistant, token: str) -> ICalConfigEntry | None:
    """Find the loaded entry matching token, in constant time per entry."""
    match = None
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if hmac.compare_digest(entry.data[CONF_TOKEN].encode(), token.encode()):
            match = entry
    return match


def _option(entry: ConfigEntry, key: str, default: int) -> int:
    return int(entry.options.get(key, default))


async def _fetch(
    hass: HomeAssistant, entry: ConfigEntry, entity_id: str
) -> list[IcsEvent] | None:
    """Return the events, or None when the calendar could not be read."""
    entity: CalendarEntity | None = hass.data[DATA_COMPONENT].get_entity(entity_id)
    if entity is None:
        _LOGGER.warning("Calendar %s not available", entity_id)
        return None
    now = dt_util.now()
    start = now - timedelta(days=_option(entry, CONF_PAST_DAYS, DEFAULT_PAST_DAYS))
    end = now + timedelta(days=_option(entry, CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS))
    try:
        events = await entity.async_get_events(hass, start, end)
    except Exception:  # noqa: BLE001 - a broken provider must not crash the view
        _LOGGER.exception("Failed to fetch events from %s", entity_id)
        return None
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


async def _render(hass: HomeAssistant, entry: ICalConfigEntry, feed: str) -> tuple[str, str] | None:
    """Return (body, etag) for a feed, or None if the feed doesn't exist."""
    if feed == ALL_FEED:
        feed_entities = entity_ids(hass, entry)
        title = entry.data[CONF_NAME]
    else:
        calendar = next((c for c in get_calendars(entry) if c[CONF_SLUG] == feed), None)
        if calendar is None:
            return None
        entity_id = resolve_entity_id(hass, calendar[CONF_REF])
        feed_entities = [entity_id]
        state = hass.states.get(entity_id)
        title = state.name if state else entity_id

    runtime = entry.runtime_data
    async with runtime.locks.setdefault(feed, asyncio.Lock()):
        # Re-check inside the lock: a concurrent request may have just refreshed it.
        cached = runtime.cache.get(feed)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1], cached[2]

        results = await asyncio.gather(*(_fetch(hass, entry, e) for e in feed_entities))
        if any(chunk is None for chunk in results):
            # An empty or partial feed would make subscribers delete their events, so
            # serve the last good copy (even if expired) or fail instead.
            if cached:
                return cached[1], cached[2]
            raise FeedUnavailableError
        events = [event for chunk in results for event in chunk]
        body = build_calendar(title, events, REFRESH_MINUTES)
        etag = f'"{hashlib.sha256(_stable(body).encode()).hexdigest()[:32]}"'
        runtime.cache[feed] = (time.monotonic(), body, etag)
        return body, etag


def _etag_matches(header: str | None, etag: str) -> bool:
    """RFC 9110 weak comparison of an If-None-Match header against our ETag."""
    if not header:
        return False
    if header.strip() == "*":
        return True
    return any(tag.strip().removeprefix("W/") == etag for tag in header.split(","))


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
        try:
            rendered = await _render(hass, entry, name)
        except FeedUnavailableError:
            return web.Response(status=503, headers={"Retry-After": str(RETRY_AFTER_SECONDS)})
        if rendered is None:
            return web.Response(status=404)
        body, etag = rendered
        headers = {
            "ETag": etag,
            "Cache-Control": f"private, max-age={CACHE_TTL_SECONDS}",
        }
        if _etag_matches(request.headers.get("If-None-Match"), etag):
            return web.Response(status=304, headers=headers)
        headers["Content-Disposition"] = f'inline; filename="{name}.ics"'
        return web.Response(
            body=body.encode(),
            content_type="text/calendar",
            charset="utf-8",
            headers=headers,
        )
