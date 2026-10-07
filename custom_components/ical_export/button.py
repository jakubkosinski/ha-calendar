"""Button to rotate the feed token."""

from __future__ import annotations

import secrets

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_TOKEN, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RegenerateTokenButton(entry)])


class RegenerateTokenButton(ButtonEntity):
    """Invalidate old feed URLs by issuing a new token."""

    _attr_has_entity_name = True
    _attr_translation_key = "regenerate_token"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_regenerate_token"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
        }

    async def async_press(self) -> None:
        # The update listener reloads the entry, which re-announces the new URLs.
        self.hass.config_entries.async_update_entry(
            self._entry,
            data={
                **self._entry.data,
                CONF_TOKEN: secrets.token_urlsafe(32),
                "announced": False,
            },
        )
