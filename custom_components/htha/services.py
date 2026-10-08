"""Services for the Ht HA integration (time programs)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CONF_WRITE_ENABLED, DOMAIN
from .timeprog import (
    build_single_entry,
    build_window_entries,
    current_entry,
    resolve_days,
    resolve_time_program,
)

if TYPE_CHECKING:
    from .coordinator import HtHACoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TIME_WINDOW = "set_time_window"
SERVICE_SET_TIME_PROGRAM_ENTRY = "set_time_program_entry"
SERVICE_REFRESH_TIME_PROGRAMS = "refresh_time_programs"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_TIME_PROGRAM = "time_program"
ATTR_DAYS = "days"
ATTR_START = "start"
ATTR_END = "end"
ATTR_STATE = "state"
ATTR_OFF_STATE = "off_state"
ATTR_ENTRY = "entry"

_PROGRAM = vol.Any(vol.Coerce(int), cv.string)
_DAYS = vol.Any(cv.string, vol.Coerce(int), [vol.Any(vol.Coerce(int), cv.string)])
_TIME = vol.Any(cv.string, cv.time)

BASE_SCHEMA = {
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
}

SET_TIME_WINDOW_SCHEMA = vol.Schema(
    {
        **BASE_SCHEMA,
        vol.Required(ATTR_TIME_PROGRAM): _PROGRAM,
        vol.Optional(ATTR_DAYS): _DAYS,
        vol.Required(ATTR_START): _TIME,
        vol.Required(ATTR_END): _TIME,
        vol.Optional(ATTR_STATE, default=1): vol.Coerce(int),
        vol.Optional(ATTR_OFF_STATE, default=0): vol.Coerce(int),
    }
)

SET_TIME_PROGRAM_ENTRY_SCHEMA = vol.Schema(
    {
        **BASE_SCHEMA,
        vol.Required(ATTR_TIME_PROGRAM): _PROGRAM,
        vol.Optional(ATTR_DAYS): _DAYS,
        vol.Required(ATTR_ENTRY): vol.Coerce(int),
        vol.Required(ATTR_STATE): vol.Coerce(int),
        vol.Required(ATTR_START): _TIME,
        vol.Required(ATTR_END): _TIME,
    }
)

REFRESH_SCHEMA = vol.Schema(BASE_SCHEMA)


def _get_entry(hass: HomeAssistant, call: ServiceCall):
    """Return the targeted (loaded) config entry."""
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
    ]
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
        if not entries:
            raise ServiceValidationError(f"No loaded Ht HA config entry with id {entry_id}")
    if not entries:
        raise ServiceValidationError("No loaded Ht HA config entry found")
    if len(entries) > 1:
        raise ServiceValidationError(
            "More than one heat pump configured, please specify config_entry_id"
        )
    return entries[0]


async def _get_program(coordinator: HtHACoordinator, program: Any) -> dict[str, Any]:
    if coordinator.time_programs is None:
        await coordinator.async_refresh_time_programs()
    try:
        return resolve_time_program(coordinator.time_programs or [], program)
    except ValueError as ex:
        raise ServiceValidationError(str(ex)) from ex


def _check_write_enabled(entry) -> None:
    if not entry.data.get(CONF_WRITE_ENABLED, False):
        raise ServiceValidationError(
            "Writing to the heat pump is disabled. Turn on the 'Allow writing' switch first."
        )


async def _write(
    coordinator: HtHACoordinator, prog: dict[str, Any], wanted: dict[tuple[int, int], Any]
) -> dict[str, Any]:
    """Write only the entries that differ from the cached program."""
    changes = [
        (day, num, entry)
        for (day, num), entry in sorted(wanted.items())
        if current_entry(prog, day, num) != entry
    ]
    if not changes:
        _LOGGER.debug("Time program %s already up to date", prog["index"])
        return {"changed_entries": 0, "time_program": prog}
    result = await coordinator.async_write_time_prog_entries(int(prog["index"]), changes)
    return {"changed_entries": len(changes), "time_program": result}


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Ht HA services."""

    async def set_time_window(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        _check_write_enabled(entry)
        coordinator: HtHACoordinator = entry.runtime_data
        prog = await _get_program(coordinator, call.data[ATTR_TIME_PROGRAM])
        try:
            days = resolve_days(call.data.get(ATTR_DAYS))
            entries = build_window_entries(
                prog,
                call.data[ATTR_START],
                call.data[ATTR_END],
                on_state=call.data[ATTR_STATE],
                off_state=call.data[ATTR_OFF_STATE],
            )
        except ValueError as ex:
            raise ServiceValidationError(str(ex)) from ex
        days = [d for d in days if d < int(prog["nod"])]
        wanted = {(day, num): e for day in days for num, e in enumerate(entries)}
        return await _write(coordinator, prog, wanted)

    async def set_time_program_entry(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        _check_write_enabled(entry)
        coordinator: HtHACoordinator = entry.runtime_data
        prog = await _get_program(coordinator, call.data[ATTR_TIME_PROGRAM])
        num = call.data[ATTR_ENTRY]
        if num not in range(int(prog["ead"])):
            raise ServiceValidationError(
                f"entry must be between 0 and {int(prog['ead']) - 1}"
            )
        try:
            days = resolve_days(call.data.get(ATTR_DAYS))
            tp_entry = build_single_entry(
                prog, call.data[ATTR_STATE], call.data[ATTR_START], call.data[ATTR_END]
            )
        except ValueError as ex:
            raise ServiceValidationError(str(ex)) from ex
        days = [d for d in days if d < int(prog["nod"])]
        wanted = {(day, num): tp_entry for day in days}
        return await _write(coordinator, prog, wanted)

    async def refresh_time_programs(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        coordinator: HtHACoordinator = entry.runtime_data
        progs = await coordinator.async_refresh_time_programs()
        return {"time_programs": progs}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TIME_WINDOW,
        set_time_window,
        schema=SET_TIME_WINDOW_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TIME_PROGRAM_ENTRY,
        set_time_program_entry,
        schema=SET_TIME_PROGRAM_ENTRY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_TIME_PROGRAMS,
        refresh_time_programs,
        schema=REFRESH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
