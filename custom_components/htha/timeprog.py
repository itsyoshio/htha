"""Helpers for reading and writing Heliotherm time programs.

This module has no Home Assistant imports so it can be unit tested on its own.
"""

from __future__ import annotations

import re
from typing import Any

from htheatpump.httimeprog import TimeProgEntry, TimeProgPeriod, TimeProgram

# Day indices as used by the heat pump (0 = Monday ... 6 = Sunday)
WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_GERMAN_DAYS: tuple[str, ...] = ("mo", "di", "mi", "do", "fr", "sa", "so")
DAY_GROUPS: dict[str, tuple[int, ...]] = {
    "all": tuple(range(7)),
    "weekdays": tuple(range(5)),
    "weekend": (5, 6),
}

_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")
END_OF_DAY = "24:00"


def normalize_time(value: Any, *, is_end: bool = False) -> str:
    """Return a time value as ``HH:MM``.

    Accepts ``HH:MM``, ``HH:MM:SS`` and ``datetime.time`` objects.
    For end times ``00:00`` is interpreted as midnight at the end of the day (``24:00``).
    """
    if hasattr(value, "hour") and hasattr(value, "minute"):
        text = f"{value.hour:02d}:{value.minute:02d}"
    else:
        text = str(value)
    m = _TIME_RE.match(text)
    if not m:
        raise ValueError(f"invalid time value {value!r}, expected HH:MM")
    hour, minute = int(m.group(1)), int(m.group(2))
    if minute > 59 or hour > 24 or (hour == 24 and minute != 0):
        raise ValueError(f"invalid time value {value!r}")
    if is_end and hour == 0 and minute == 0:
        hour = 24
    return f"{hour:02d}:{minute:02d}"


def resolve_days(days: Any) -> list[int]:
    """Translate a day specification into a sorted list of day indices (0 = Monday)."""
    if days is None:
        return list(DAY_GROUPS["all"])
    if isinstance(days, (str, int)):
        days = [days]
    result: set[int] = set()
    for day in days:
        if isinstance(day, int) or (isinstance(day, str) and day.strip().isdigit()):
            idx = int(day)
            if idx not in range(7):
                raise ValueError(f"invalid day index {day!r}, expected 0..6")
            result.add(idx)
            continue
        key = str(day).strip().lower()
        if key in DAY_GROUPS:
            result.update(DAY_GROUPS[key])
        elif key[:3] in WEEKDAYS:
            result.add(WEEKDAYS.index(key[:3]))
        elif key[:2] in _GERMAN_DAYS:
            result.add(_GERMAN_DAYS.index(key[:2]))
        else:
            raise ValueError(f"invalid day {day!r}")
    return sorted(result)


def resolve_time_program(time_programs: list[dict[str, Any]], program: Any) -> dict[str, Any]:
    """Find a cached time program (JSON form) by index or (case-insensitive) name."""
    if isinstance(program, int) or (isinstance(program, str) and program.strip().isdigit()):
        idx = int(program)
        for prog in time_programs:
            if prog["index"] == idx:
                return prog
        raise ValueError(f"no time program with index {idx}")
    name = str(program).strip().lower()
    for prog in time_programs:
        if prog["name"].lower() == name:
            return prog
    matches = [p for p in time_programs if p["name"].lower().startswith(name)]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(f"{p['index']}={p['name']}" for p in time_programs)
    raise ValueError(f"unknown time program {program!r} (available: {available})")


def build_window_entries(
    prog: dict[str, Any],
    start: str,
    end: str,
    on_state: int = 1,
    off_state: int = 0,
) -> list[TimeProgEntry]:
    """Build the complete list of entries for one day with a single active window.

    The day is split into up to three periods (off / on / off); remaining entries are
    filled with ``24:00-24:00`` like the heat pump does for unused entries.
    """
    start = normalize_time(start)
    end = normalize_time(end, is_end=True)
    if _minutes(start) >= _minutes(end):
        raise ValueError(f"start ({start}) must be before end ({end})")

    periods: list[tuple[int, str, str]] = []
    if start != "00:00":
        periods.append((off_state, "00:00", start))
    periods.append((on_state, start, end))
    if end != END_OF_DAY:
        periods.append((off_state, end, END_OF_DAY))

    ead = int(prog["ead"])
    if len(periods) > ead:
        raise ValueError(f"time program only supports {ead} entries a day")
    while len(periods) < ead:
        periods.append((off_state, END_OF_DAY, END_OF_DAY))

    entries = [TimeProgEntry(state, TimeProgPeriod.from_str(beg, fin)) for state, beg, fin in periods]
    validate_entries(prog, entries)
    return entries


def build_day_entries(prog: dict[str, Any], periods: list[dict[str, Any]]) -> list[TimeProgEntry]:
    """Build the complete list of entries for one day from a list of periods.

    ``periods`` is a list of ``{"state": int, "start": "HH:MM", "end": "HH:MM"}``.
    Periods are sorted by start time, must not overlap and must not be empty.
    Unused entries are filled with ``24:00-24:00`` (state 0) like the heat pump does.
    """
    ead = int(prog["ead"])
    parsed: list[tuple[int, str, str]] = []
    for period in periods:
        start = normalize_time(period["start"])
        end = normalize_time(period["end"], is_end=True)
        if start == end:
            continue  # ignore empty periods (e.g. 24:00-24:00 placeholders)
        if _minutes(start) > _minutes(end):
            raise ValueError(f"start ({start}) must be before end ({end})")
        parsed.append((int(period.get("state", 0)), start, end))
    parsed.sort(key=lambda p: _minutes(p[1]))
    for prev, cur in zip(parsed, parsed[1:]):
        if _minutes(cur[1]) < _minutes(prev[2]):
            raise ValueError(f"periods overlap: {prev[1]}-{prev[2]} and {cur[1]}-{cur[2]}")
    # Cover the whole day like the heat pump does: fill gaps with state 0 ...
    filled: list[tuple[int, str, str]] = []
    cursor = "00:00"
    for state, start, end in parsed:
        if _minutes(start) > _minutes(cursor):
            filled.append((0, cursor, start))
        filled.append((state, start, end))
        cursor = end
    if _minutes(cursor) < _minutes(END_OF_DAY):
        filled.append((0, cursor, END_OF_DAY))
    # ... and merge adjacent periods with the same state to save entries
    parsed = []
    for state, start, end in filled:
        if parsed and parsed[-1][0] == state and parsed[-1][2] == start:
            parsed[-1] = (state, parsed[-1][1], end)
        else:
            parsed.append((state, start, end))
    if len(parsed) > ead:
        raise ValueError(f"time program only supports {ead} entries a day")
    while len(parsed) < ead:
        parsed.append((0, END_OF_DAY, END_OF_DAY))
    entries = [TimeProgEntry(state, TimeProgPeriod.from_str(beg, fin)) for state, beg, fin in parsed]
    validate_entries(prog, entries)
    return entries


def build_single_entry(prog: dict[str, Any], state: int, start: str, end: str) -> TimeProgEntry:
    """Build and validate a single time program entry."""
    entry = TimeProgEntry(int(state), TimeProgPeriod.from_str(normalize_time(start), normalize_time(end, is_end=True)))
    validate_entries(prog, [entry])
    return entry


def validate_entries(prog: dict[str, Any], entries: list[TimeProgEntry]) -> None:
    """Validate entries against the time program limits (states and step size)."""
    checker = TimeProgram(
        int(prog["index"]), prog["name"], int(prog["ead"]), int(prog["nos"]), int(prog["ste"]), int(prog["nod"])
    )
    for num, entry in enumerate(entries):
        checker.set_entry(0, num % checker.entries_a_day, entry)  # raises ValueError


def current_entry(prog: dict[str, Any], day: int, num: int) -> TimeProgEntry | None:
    """Return the cached entry of a program, or None if not known."""
    try:
        raw = prog["entries"][day][num]
    except (KeyError, IndexError, TypeError):
        return None
    if raw is None:
        return None
    return TimeProgEntry.from_json(raw)


def active_windows(prog: dict[str, Any], day: int, on_state: int = 1) -> list[tuple[str, str]]:
    """Return the merged active windows (start, end) of a day from the cached program."""
    windows: list[list[str]] = []
    for num in range(int(prog.get("ead", 0))):
        entry = current_entry(prog, day, num)
        if entry is None or entry.state != on_state:
            continue
        start, end = entry.period.start_str, entry.period.end_str
        if start == end:
            continue
        if windows and windows[-1][1] == start:
            windows[-1][1] = end
        else:
            windows.append([start, end])
    return [(s, e) for s, e in windows]


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)
