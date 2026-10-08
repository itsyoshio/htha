"""Datetime platform for the Ht HA integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.datetime import (
    DateTimeEntity,
    DateTimeEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HtHAConfigEntry
from .entity import HtHAEntity

_LOGGER = logging.getLogger(__name__)

# key "datetime" keeps the unique id "<entry_id>_datetime" of earlier versions
HT_DATETIME_DESCRIPTION = DateTimeEntityDescription(
    key="datetime",
    translation_key="ht_datetime",
    icon="mdi:clock-outline",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: HtHAConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ht HA datetime entities from a config entry."""
    coordinator = config_entry.runtime_data
    async_add_entities([HtHADateTimeEntity(coordinator, config_entry, HT_DATETIME_DESCRIPTION)])


class HtHADateTimeEntity(HtHAEntity, DateTimeEntity):
    """Clock of the heat pump.

    The clock is read from the heat pump hourly (together with the time programs)
    and whenever it is set. In between, the value is extrapolated from the last read.
    Setting a value writes it to the heat pump.
    """

    @property
    def native_value(self) -> datetime | None:
        """Return the (extrapolated) heat pump date/time."""
        ht_dt = self.coordinator.ht_datetime
        read_at = self.coordinator.ht_datetime_read_at
        if ht_dt is None or read_at is None:
            return None
        value = ht_dt + (dt_util.now() - read_at)
        return value.replace(second=0, microsecond=0)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return offset to Home Assistant time and when the clock was read."""
        ht_dt = self.coordinator.ht_datetime
        read_at = self.coordinator.ht_datetime_read_at
        if ht_dt is None or read_at is None:
            return None
        return {
            "offset_seconds": round((ht_dt - read_at).total_seconds()),
            "last_read": read_at.isoformat(timespec="seconds"),
        }

    async def async_set_value(self, value: datetime) -> None:
        """Write a new date/time to the heat pump."""
        result = await self.coordinator.async_set_datetime(dt_util.as_local(value))
        if result is None:
            raise HomeAssistantError("Failed to set the heat pump date/time")
        self.coordinator.async_update_listeners()
