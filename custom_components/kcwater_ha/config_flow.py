"""Config flow for the Kansas City Water integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    KCWaterApiClient,
    KCWaterApiClientAuthenticationError,
    KCWaterApiClientCommunicationError,
)
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class KCWaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kansas City Water."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate_login(self.hass, user_input)
            if not errors:
                self._async_abort_entries_match(
                    {
                        CONF_USERNAME: user_input[CONF_USERNAME],
                    }
                )
                return self.async_create_entry(
                    title=f"Kansas City Water ({user_input[CONF_USERNAME]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


async def _validate_login(
    hass: HomeAssistant, login_data: dict[str, Any]
) -> dict[str, Any]:
    """Validate login data and return any errors."""
    api = KCWaterApiClient(
        login_data[CONF_USERNAME],
        login_data[CONF_PASSWORD],
        async_create_clientsession(hass),
    )

    errors: dict[str, str] = {}
    try:
        await api.async_login()
    except KCWaterApiClientAuthenticationError:
        _LOGGER.exception("Invalid auth when connecting to kcwater.us")
        errors["base"] = "invalid_auth"
    except KCWaterApiClientCommunicationError:
        _LOGGER.exception("Could not connect to kcwater.us")
        errors["base"] = "cannot_connect"
    return errors
