"""Custom types for integration_blueprint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .api import KCWaterApiClient

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import KCWaterApiClient
    from .coordinator import KCWaterUpdateCoordinator


type KCWaterConfigEntry = ConfigEntry[KCWaterData]


@dataclass
class KCWaterData:
    """Data for the Blueprint integration."""

    client: KCWaterApiClient
    coordinator: KCWaterUpdateCoordinator
    integration: Integration
    username: str
