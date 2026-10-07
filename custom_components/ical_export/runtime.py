"""Per-entry runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry


@dataclass
class FeedRuntime:
    """Rendered feeds of one config entry, keyed by feed name."""

    # feed -> (monotonic timestamp, body, etag)
    cache: dict[str, tuple[float, str, str]] = field(default_factory=dict)


type ICalConfigEntry = ConfigEntry[FeedRuntime]
