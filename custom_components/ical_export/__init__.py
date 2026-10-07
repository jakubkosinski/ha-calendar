"""iCal Export: subscribable .ics feeds of Home Assistant calendars."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.typing import ConfigType

from .const import CONF_CALENDARS, CONF_TOKEN, DOMAIN
from .views import ALL_FEED, ICalFeedView

PLATFORMS = ["button"]
CONF_ANNOUNCED = "announced"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the HTTP view once."""
    hass.data.setdefault(DOMAIN, {"cache": {}})
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


def _announce(hass: HomeAssistant, entry: ConfigEntry) -> None:
    lines = []
    for name, url in feed_urls(hass, entry).items():
        lines.append(f"**{name}**\n\n`{url}`\n\n`{url.replace('https://', 'webcal://', 1)}`")
    persistent_notification.async_create(
        hass,
        "Add these as subscriptions in Apple Calendar. Treat the URLs like passwords.\n\n"
        + "\n\n".join(lines),
        title=f"iCal Export: {entry.title}",
        notification_id=f"{DOMAIN}_{entry.entry_id}",
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a feed."""
    if not entry.data.get(CONF_ANNOUNCED):
        _announce(hass, entry)
        # Done before registering the update listener, so no reload is triggered.
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_ANNOUNCED: True})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a feed."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        cache = hass.data[DOMAIN]["cache"]
        for key in [k for k in cache if k[0] == entry.entry_id]:
            del cache[key]
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Dismiss the notification when a feed is removed."""
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_{entry.entry_id}")
