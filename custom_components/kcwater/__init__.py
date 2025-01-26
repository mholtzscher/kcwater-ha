"""The Kansas City Water integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import KCWaterApiClient
from .const import DOMAIN, LOGGER
from .coordinator import KCWaterUpdateCoordinator
from .data import KCWaterData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_PLATFORMS: list[Platform] = [Platform.SENSOR]

type KCWaterConfigEntry = ConfigEntry[KCWaterData]


async def async_setup_entry(hass: HomeAssistant, entry: KCWaterConfigEntry) -> bool:
    """Set up Kansas City Water from a config entry."""
    coordinator = KCWaterUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(minutes=1),
    )
    entry.runtime_data = KCWaterData(
        client=KCWaterApiClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            session=async_get_clientsession(hass),
        ),
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
        username=entry.data[CONF_USERNAME],
    )

    await coordinator.async_config_entry_first_refresh()

    return True
