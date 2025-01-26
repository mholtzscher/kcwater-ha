"""DataUpdateCoordinator for Kansas City Water."""

from __future__ import annotations

from datetime import datetime, timedelta
from operator import attrgetter
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    import logging

    from .api import Reading
    from .data import KCWaterConfigEntry


# https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
class KCWaterUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    config_entry: KCWaterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the data handler."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self._statistic_ids: set = set()

        @callback
        def _dummy_listener() -> None:
            pass

        # Force the coordinator to periodically update by registering at least one listener.
        # Needed when the _async_update_data below returns {} for utilities that don't provide
        # forecast, which results to no sensors added, no registered listeners, and thus
        # _async_update_data not periodically getting called which is needed for _insert_statistics.
        self.async_add_listener(_dummy_listener)
        # self.config_entry.async_on_unload(self._clear_statistics)

    def _clear_statistics(self) -> None:
        """Clear statistics."""
        get_instance(self.hass).async_clear_statistics(list(self._statistic_ids))

    async def _async_update_data(self) -> Any:
        """Update data via library."""
        LOGGER.info("Updating data for %s", DOMAIN)
        account_number = (
            await self.config_entry.runtime_data.client.get_account_number()
        )
        consumption_statistic_id = f"{DOMAIN}:{account_number}_water_consumption"
        self._statistic_ids.add(consumption_statistic_id)
        last_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, consumption_statistic_id, True, set()
        )
        if not last_stat:
            LOGGER.debug("Updating statistic for the first time")
            usage: list[Reading] = []
            start = datetime.now() - timedelta(days=31)
            end = datetime.now() - timedelta(days=1)
            usage = await self.config_entry.runtime_data.client.async_get_data(
                start, end
            )
            consumption_sum = 0.0
            last_stats_time = None
        else:
            start = datetime.now() - timedelta(days=2)
            end = datetime.now() - timedelta(days=1)
            usage = await self.config_entry.runtime_data.client.async_get_data(
                start, end
            )
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                min(usage, key=attrgetter("read_datetime")).read_datetime,
                None,
                {consumption_statistic_id},
                "hour",
                None,
                {"sum"},
            )
            consumption_sum = cast(float, stats[consumption_statistic_id][0]["sum"])
            last_stats_time = stats[consumption_statistic_id][0]["start"]

        consumption_statistics = []
        for item in usage:
            if (
                last_stats_time is not None
                and item.read_datetime.timestamp() <= last_stats_time
            ):
                LOGGER.debug("Skipping %s", item.read_datetime)
                continue
            consumption_sum += item.raw_consumption
            consumption_statistics.append(
                StatisticData(
                    start=item.read_datetime,
                    state=item.raw_consumption,
                    sum=consumption_sum,
                )
            )

        name_prefix = f"Kansas City Water {account_number}"
        consumption_metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"{name_prefix} Consumption",
            source=DOMAIN,
            statistic_id=consumption_statistic_id,
            unit_of_measurement=UnitOfVolume.CUBIC_FEET,
        )

        LOGGER.debug(
            "Adding %s statistics for %s",
            len(consumption_statistics),
            consumption_statistic_id,
        )
        async_add_external_statistics(
            self.hass, consumption_metadata, consumption_statistics
        )
