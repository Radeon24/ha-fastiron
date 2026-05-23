"""Config flow pour l'intégration FastIron."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import FastIronAPI, FastIronAuthError, FastIronConnectionError
from .const import (
    CONF_ENABLE_DIAGNOSTIC_SENSORS,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_ENABLE_DIAGNOSTIC_SENSORS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    ENTRY_SW_FIRMWARE,
    ENTRY_SW_HOSTNAME,
    ENTRY_SW_MODEL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)


async def _validate_and_discover(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Tente de se connecter au switch et retourne ses informations système."""
    api = FastIronAPI(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        verify_ssl=data[CONF_VERIFY_SSL],
    )
    try:
        info = await api.get_system_info()
        return {
            ENTRY_SW_HOSTNAME: info.get("hostname", data[CONF_HOST]),
            ENTRY_SW_MODEL: info.get("model", "FastIron"),
            ENTRY_SW_FIRMWARE: info.get("firmwareVersion", ""),
        }
    finally:
        await api.close()


class FastIronConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Flux de configuration pour un switch FastIron."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return FastIronOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                discovered = await _validate_and_discover(self.hass, user_input)
            except FastIronAuthError:
                errors["base"] = "invalid_auth"
            except FastIronConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Erreur inattendue lors de la validation")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                title = discovered.get(ENTRY_SW_HOSTNAME, user_input[CONF_HOST])
                return self.async_create_entry(
                    title=title,
                    data={**user_input, **discovered},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class FastIronOptionsFlow(config_entries.OptionsFlow):
    """Options flow pour FastIron : paramètres modifiables sans reconfigurer."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=10, max=3600)),
                vol.Optional(
                    CONF_ENABLE_DIAGNOSTIC_SENSORS,
                    default=opts.get(
                        CONF_ENABLE_DIAGNOSTIC_SENSORS, DEFAULT_ENABLE_DIAGNOSTIC_SENSORS
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
