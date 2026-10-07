"""Config and options flow."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import feed_urls, webcal_url
from .const import (
    CONF_CALENDARS,
    CONF_FUTURE_DAYS,
    CONF_NAME,
    CONF_PAST_DAYS,
    CONF_TOKEN,
    DEFAULT_FUTURE_DAYS,
    DEFAULT_PAST_DAYS,
    DOMAIN,
)

INSECURE_WARNING = (
    "**Warning:** these URLs are not HTTPS (or HA's address could not be determined), so "
    "the secret token would travel unencrypted. Set an HTTPS *External URL* in "
    "*Settings → System → Network* before subscribing from outside your home network.\n\n"
)

_CALENDARS = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="calendar", multiple=True)
)


def _days(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


class ICalExportConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a feed."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ICalExportOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CALENDARS]:
                errors[CONF_CALENDARS] = "no_calendars"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_CALENDARS: user_input[CONF_CALENDARS],
                        CONF_TOKEN: secrets.token_urlsafe(32),
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Home Assistant"): str,
                    vol.Required(CONF_CALENDARS): _CALENDARS,
                }
            ),
            errors=errors,
        )


class ICalExportOptionsFlow(OptionsFlow):
    """Edit settings, show feed URLs and rotate the token (admin only)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["settings", "urls", "regenerate"])

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CALENDARS]:
                errors[CONF_CALENDARS] = "no_calendars"
            else:
                return self.async_create_entry(
                    data={
                        CONF_CALENDARS: user_input[CONF_CALENDARS],
                        CONF_PAST_DAYS: int(user_input[CONF_PAST_DAYS]),
                        CONF_FUTURE_DAYS: int(user_input[CONF_FUTURE_DAYS]),
                    }
                )
        current = {**entry.data, **entry.options}
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CALENDARS, default=current[CONF_CALENDARS]): _CALENDARS,
                    vol.Required(
                        CONF_PAST_DAYS,
                        default=current.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS),
                    ): _days(0, 365),
                    vol.Required(
                        CONF_FUTURE_DAYS,
                        default=current.get(CONF_FUTURE_DAYS, DEFAULT_FUTURE_DAYS),
                    ): _days(1, 1825),
                }
            ),
            errors=errors,
        )

    async def async_step_urls(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=dict(self.config_entry.options))
        urls = feed_urls(self.hass, self.config_entry)
        blocks = [f"**{name}**\n\n`{url}`\n\n`{webcal_url(url)}`" for name, url in urls.items()]
        insecure = not all(url.startswith("https://") for url in urls.values())
        return self.async_show_form(
            step_id="urls",
            data_schema=vol.Schema({}),
            description_placeholders={
                "urls": "\n\n".join(blocks),
                "warning": INSECURE_WARNING if insecure else "",
            },
        )

    async def async_step_regenerate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="regenerate", data_schema=vol.Schema({}))
        # The update listener reloads the entry, which drops the old token for good.
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_TOKEN: secrets.token_urlsafe(32)},
        )
        return await self.async_step_urls()
