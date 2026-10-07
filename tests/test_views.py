"""Tests for views, config flow and token rotation."""

from unittest.mock import patch

from homeassistant.components.calendar import DATA_COMPONENT, CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.ical_export.const import (
    CONF_CALENDARS,
    CONF_NAME,
    CONF_TOKEN,
    DOMAIN,
)

TOKEN = "secret-token"


class _Cal(CalendarEntity):
    _attr_name = "Demo"
    _attr_unique_id = "demo-cal"

    @property
    def event(self):
        return None

    async def async_get_events(self, hass, start_date, end_date):
        return []


async def _setup(hass: HomeAssistant, calendars=("calendar.demo",)) -> MockConfigEntry:
    assert await async_setup_component(hass, "calendar", {})
    await hass.data[DATA_COMPONENT].async_add_entities([_Cal()])
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Feed",
        data={
            CONF_NAME: "Feed",
            CONF_CALENDARS: list(calendars),
            CONF_TOKEN: TOKEN,
            "announced": True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _event(summary="Demo"):
    now = dt_util.now()
    return CalendarEvent(start=now, end=now, summary=summary, uid="u1")


async def test_feed_ok_404_and_etag(
    hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator
):
    entry = await _setup(hass)
    client = await hass_client_no_auth()
    entity = hass.data[DATA_COMPONENT].get_entity("calendar.demo")
    entity_id = entity.entity_id if entity else None
    assert entity_id == "calendar.demo"

    with patch.object(type(entity), "async_get_events", return_value=[_event()]):
        resp = await client.get(f"/api/ical_export/{TOKEN}/all.ics")
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("text/calendar")
        body = await resp.text()
        assert "SUMMARY:Demo" in body
        etag = resp.headers["ETag"]

        resp = await client.get(
            f"/api/ical_export/{TOKEN}/all.ics", headers={"If-None-Match": etag}
        )
        assert resp.status == 304

        resp = await client.get(f"/api/ical_export/{TOKEN}/demo.ics")
        assert resp.status == 200

    assert (await client.get("/api/ical_export/wrong/all.ics")).status == 404
    assert (await client.get(f"/api/ical_export/{TOKEN}/other.ics")).status == 404
    assert entry.state is ConfigEntryState.LOADED


async def test_failing_calendar_without_cache_returns_503(
    hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator
):
    await _setup(hass)
    client = await hass_client_no_auth()
    entity = hass.data[DATA_COMPONENT].get_entity("calendar.demo")
    with patch.object(type(entity), "async_get_events", side_effect=RuntimeError("boom")):
        resp = await client.get(f"/api/ical_export/{TOKEN}/all.ics")
    assert resp.status == 503
    assert "Retry-After" in resp.headers


async def test_failing_calendar_serves_stale_copy(
    hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator
):
    await _setup(hass)
    client = await hass_client_no_auth()
    entity = hass.data[DATA_COMPONENT].get_entity("calendar.demo")
    url = f"/api/ical_export/{TOKEN}/all.ics"
    with patch.object(type(entity), "async_get_events", return_value=[_event()]):
        good = await client.get(url)
    assert good.status == 200
    good_body, good_etag = await good.text(), good.headers["ETag"]

    # Expire the cache, then break the provider.
    cache = hass.data[DOMAIN]["cache"]
    for key, (_, body, etag) in list(cache.items()):
        cache[key] = (-1e9, body, etag)
    with patch.object(type(entity), "async_get_events", side_effect=RuntimeError("boom")):
        resp = await client.get(url)
    assert resp.status == 200
    assert resp.headers["ETag"] == good_etag
    assert await resp.text() == good_body


async def test_token_rotation_invalidates_old_url(
    hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator
):
    entry = await _setup(hass)
    client = await hass_client_no_auth()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "regenerate"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    new = entry.data[CONF_TOKEN]
    assert new != TOKEN
    # The rotation ends on the URL step, which shows the new token.
    assert result["step_id"] == "urls"
    assert new in result["description_placeholders"]["urls"]
    assert (await client.get(f"/api/ical_export/{TOKEN}/all.ics")).status == 404
    assert (await client.get(f"/api/ical_export/{new}/all.ics")).status == 200


async def test_notification_does_not_leak_token(hass: HomeAssistant):
    assert await async_setup_component(hass, "calendar", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Family", CONF_CALENDARS: ["calendar.demo"]}
    )
    await hass.async_block_till_done()
    token = result["data"][CONF_TOKEN]
    notifications = hass.data["persistent_notification"]
    assert notifications
    assert all(token not in n["message"] for n in notifications.values())


async def test_config_flow_and_options(hass: HomeAssistant):
    assert await async_setup_component(hass, "calendar", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Family", CONF_CALENDARS: ["calendar.demo"]},
    )
    assert result["type"] == "create_entry"
    assert len(result["data"][CONF_TOKEN]) >= 32
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CALENDARS: ["calendar.demo"], "past_days": 7, "future_days": 90},
    )
    assert result["type"] == "create_entry"
    assert entry.options["past_days"] == 7
