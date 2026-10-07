"""iCal Export: subscribable .ics feeds of Home Assistant calendars."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.typing import ConfigType

from .const import CONF_CALENDARS, CONF_TOKEN, DOMAIN
from .runtime import FeedRuntime, ICalConfigEntry
from .views import ALL_FEED, ICalFeedView

CONF_ANNOUNCED = "announced"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the HTTP view once."""
    hass.http.register_view(ICalFeedView())
    return True


def feed_urls(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Return feed name -> https URL for an entry."""
    try:
        base = get_url(hass, prefer_external=True)
    except NoURLAvailableError:
        base = "http://<home-assistant-host>:8123"
    prefix = f"{base}/api/{DOMAIN}/{entry.data[CONF_TOKEN]}"
    calendars = entry.options.get(CONF_CALENDARS, entry.data[CONF_CALENDARS])
    urls = {ALL_FEED: f"{prefix}/{ALL_FEED}.ics"}
    for entity_id in calendars:
        object_id = entity_id.split(".", 1)[1]
        urls[object_id] = f"{prefix}/{object_id}.ics"
    return urls


def webcal_url(url: str) -> str:
    """Return the webcal:// form of an http(s) URL."""
    return "webcal://" + url.split("://", 1)[1]


def _announce(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # The URLs contain the secret token and a notification is visible to every user,
    # so they are only shown in the options flow, which requires an admin.
    persistent_notification.async_create(
        hass,
        "The feed is ready. Open *Settings → Devices & services → iCal Export → Configure "
        "→ Show feed URLs* to get the addresses to subscribe to in Apple Calendar.",
        title=f"iCal Export: {entry.title}",
        notification_id=f"{DOMAIN}_{entry.entry_id}",
    )


def _remove_legacy_button(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the token-rotation button (and its device) that older versions created."""
    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        ent_reg.async_remove(entity.entity_id)
    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        dev_reg.async_remove_device(device.id)


async def async_setup_entry(hass: HomeAssistant, entry: ICalConfigEntry) -> bool:
    """Set up a feed."""
    entry.runtime_data = FeedRuntime()
    _remove_legacy_button(hass, entry)
    if not entry.data.get(CONF_ANNOUNCED):
        _announce(hass, entry)
        # Done before registering the update listener, so no reload is triggered.
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_ANNOUNCED: True})
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ICalConfigEntry) -> bool:
    """Unload a feed; its runtime data (cache) goes away with it."""
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Dismiss the notification when a feed is removed."""
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_{entry.entry_id}")
