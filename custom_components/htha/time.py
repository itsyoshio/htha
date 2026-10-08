"""Time platform for the Ht HA integration.

Exposes the active window (start/end) of on/off time programs such as
"Warmwasser" and "Zirkulationspumpe" as time entities. The displayed value is
today's window; setting a value applies the window to every day of the program.
"""

from __future__ import annotations

import logging
from datetime import time as dt_time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HtHAConfigEntry
from .const import CONF_WRITE_ENABLED
from .entity import HtHAEntity
from .services import write_wanted_entries
from .timeprog import active_windows, build_window_entries

_LOGGER = logging.getLogger(__name__)

# English names for the time programs reported by the heat pump
PROGRAM_NAMES: dict[str, str] = {
    "warmwasser": "Hot Water",
    "zirkulationspumpe": "Circulation Pump",
    "zirkulation": "Circulation Pump",
    "heizung": "Heating",
    "mischer 1": "Mixer 1",
    "mischer 2": "Mixer 2",
}

ON_STATE = 1
OFF_STATE = 0


def _program_label(name: str, index: int) -> str:
    return PROGRAM_NAMES.get(name.strip().lower(), name.strip() or f"Time Program {index}")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: HtHAConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up time entities for all on/off time programs."""
    coordinator = config_entry.runtime_data
    progs = coordinator.time_programs or []
    if not progs:
        _LOGGER.warning("No time programs available, time entities not created")
        return

    entities: list[HtHATimeProgramWindowEntity] = []
    for prog in progs:
        if int(prog.get("nos", 0)) != 2:
            # only simple on/off programs (e.g. hot water, circulation pump)
            continue
        label = _program_label(prog["name"], int(prog["index"]))
        for bound in ("start", "end"):
            entities.append(
                HtHATimeProgramWindowEntity(coordinator, config_entry, int(prog["index"]), label, bound)
            )
    async_add_entities(entities)


class HtHATimeProgramWindowEntity(HtHAEntity, TimeEntity):
    """Start or end of the active window of a time program."""

    def __init__(
        self,
        coordinator,
        config_entry: HtHAConfigEntry,
        index: int,
        label: str,
        bound: str,
    ) -> None:
        description = EntityDescription(
            key=f"time_program_{index}_window_{bound}",
            icon="mdi:clock-start" if bound == "start" else "mdi:clock-end",
        )
        super().__init__(coordinator, config_entry, description)
        self._index = index
        self._bound = bound
        self._attr_name = f"{label} Window {bound.capitalize()}"

    # -- helpers -------------------------------------------------------------
    def _program(self) -> dict[str, Any] | None:
        for prog in self.coordinator.time_programs or []:
            if int(prog.get("index", -1)) == self._index:
                return prog
        return None

    def _windows(self, prog: dict[str, Any], day: int) -> list[tuple[str, str]]:
        return active_windows(prog, day, ON_STATE)

    @staticmethod
    def _to_time(hhmm: str) -> dt_time:
        hour, minute = (int(v) for v in hhmm.split(":"))
        return dt_time(0, 0) if hour == 24 else dt_time(hour, minute)

    # -- state ---------------------------------------------------------------
    @property
    def available(self) -> bool:
        return super().available and self._program() is not None

    @property
    def native_value(self) -> dt_time | None:
        prog = self._program()
        if prog is None:
            return None
        windows = self._windows(prog, dt_util.now().weekday())
        if not windows:
            return None
        start, end = windows[0][0], windows[0][1]
        return self._to_time(start if self._bound == "start" else end)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        prog = self._program()
        if prog is None:
            return None
        per_day = [
            ", ".join(f"{s}-{e}" for s, e in self._windows(prog, day)) or "off"
            for day in range(int(prog.get("nod", 7)))
        ]
        return {
            "time_program": prog.get("name"),
            "time_program_index": self._index,
            "windows_per_day": per_day,
            "same_every_day": len(set(per_day)) == 1,
        }

    # -- writing -------------------------------------------------------------
    async def async_set_value(self, value: dt_time) -> None:
        if not self._config_entry.data.get(CONF_WRITE_ENABLED, False):
            raise ServiceValidationError(
                "Writing to the heat pump is disabled. Turn on the 'Allow writing' switch first."
            )
        prog = self._program()
        if prog is None:
            raise HomeAssistantError("Time program not available")

        windows = self._windows(prog, dt_util.now().weekday())
        current_start, current_end = windows[0] if windows else ("00:00", "24:00")
        new = f"{value.hour:02d}:{value.minute:02d}"
        start, end = (new, current_end) if self._bound == "start" else (current_start, new)

        try:
            entries = build_window_entries(prog, start, end, on_state=ON_STATE, off_state=OFF_STATE)
        except ValueError as ex:
            raise ServiceValidationError(str(ex)) from ex

        wanted = {
            (day, num): entry
            for day in range(int(prog["nod"]))
            for num, entry in enumerate(entries)
        }
        await write_wanted_entries(self.coordinator, prog, wanted)
