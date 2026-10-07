"""Calendars of a feed, stored by entity registry id so a rename doesn't break the feed.

Each calendar is stored as ``{"slug": ..., "ref": ...}``. ``slug`` is the stable name used in
the feed URL and ``ref`` is the entity registry id (or the entity_id for entities that have no
registry entry, e.g. without a unique id).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_CALENDARS

CONF_SLUG = "slug"
CONF_REF = "ref"


def get_calendars(entry: ConfigEntry) -> list[dict[str, str]]:
    """Return the configured calendars (options override the initial data)."""
    return entry.options.get(CONF_CALENDARS, entry.data.get(CONF_CALENDARS, []))


def resolve_entity_id(hass: HomeAssistant, ref: str) -> str:
    """Return the current entity_id for a stored reference."""
    registry_entry = er.async_get(hass).async_get(ref)
    return registry_entry.entity_id if registry_entry else ref


def entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    return [resolve_entity_id(hass, c[CONF_REF]) for c in get_calendars(entry)]


def build_calendars(
    hass: HomeAssistant,
    selected: list[str],
    existing: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Turn selected entity_ids into stored calendars, keeping slugs that already exist."""
    registry = er.async_get(hass)
    known = {c[CONF_REF]: c[CONF_SLUG] for c in existing or []}
    used: set[str] = set()
    result: list[dict[str, str]] = []
    for entity_id in selected:
        registry_entry = registry.async_get(entity_id)
        ref = registry_entry.id if registry_entry else entity_id
        slug = known.get(ref) or entity_id.split(".", 1)[1]
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}_{n}", n + 1
        used.add(slug)
        result.append({CONF_SLUG: slug, CONF_REF: ref})
    return result


def migrate_calendars(hass: HomeAssistant, value: Any) -> Any:
    """Convert a v1 list of entity_ids; slugs equal the old URL names, so URLs keep working."""
    if not isinstance(value, list) or all(isinstance(c, dict) for c in value):
        return value
    return build_calendars(hass, value)
