"""Tests for the time program helpers (no Home Assistant needed)."""

from __future__ import annotations

import datetime
import importlib.util
import pathlib

import pytest
from htheatpump.httimeprog import TimeProgEntry

_spec = importlib.util.spec_from_file_location(
    "htha_timeprog", pathlib.Path(__file__).parent / "custom_components" / "htha" / "timeprog.py"
)
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)

PROGS = [
    {
        "index": 0,
        "name": "Warmwasser",
        "ead": 7,
        "nos": 2,
        "ste": 15,
        "nod": 7,
        "entries": [
            [
                {"state": 0, "start": "00:00", "end": "08:30"},
                {"state": 1, "start": "08:30", "end": "19:00"},
                {"state": 0, "start": "19:00", "end": "24:00"},
            ]
            + [{"state": 0, "start": "24:00", "end": "24:00"}] * 4
        ]
        * 7,
    },
    {"index": 1, "name": "Zirkulationspumpe", "ead": 7, "nos": 2, "ste": 15, "nod": 7, "entries": []},
    {"index": 2, "name": "Heizung", "ead": 7, "nos": 3, "ste": 15, "nod": 7, "entries": []},
]


def test_normalize_time():
    assert tp.normalize_time("8:30") == "08:30"
    assert tp.normalize_time("08:30:00") == "08:30"
    assert tp.normalize_time(datetime.time(11, 15)) == "11:15"
    assert tp.normalize_time("00:00", is_end=True) == "24:00"
    assert tp.normalize_time("24:00") == "24:00"
    with pytest.raises(ValueError):
        tp.normalize_time("24:15")
    with pytest.raises(ValueError):
        tp.normalize_time("abc")


def test_resolve_days():
    assert tp.resolve_days(None) == list(range(7))
    assert tp.resolve_days("weekdays") == [0, 1, 2, 3, 4]
    assert tp.resolve_days(["sat", "sun"]) == [5, 6]
    assert tp.resolve_days(["Montag", "Mittwoch", "Sonntag"]) == [0, 2, 6]
    assert tp.resolve_days([0, "1", "friday"]) == [0, 1, 4]
    with pytest.raises(ValueError):
        tp.resolve_days(["funday"])
    with pytest.raises(ValueError):
        tp.resolve_days([7])


def test_resolve_time_program():
    assert tp.resolve_time_program(PROGS, 1)["name"] == "Zirkulationspumpe"
    assert tp.resolve_time_program(PROGS, "0")["name"] == "Warmwasser"
    assert tp.resolve_time_program(PROGS, "warmwasser")["index"] == 0
    assert tp.resolve_time_program(PROGS, "Zirk")["index"] == 1
    with pytest.raises(ValueError):
        tp.resolve_time_program(PROGS, "Pool")


def test_build_window_entries_regular():
    entries = tp.build_window_entries(PROGS[0], "11:00", "15:00")
    assert [str(e) for e in entries][:3] == [
        str(TimeProgEntry.from_str("0", "00:00", "11:00")),
        str(TimeProgEntry.from_str("1", "11:00", "15:00")),
        str(TimeProgEntry.from_str("0", "15:00", "24:00")),
    ]
    assert len(entries) == 7
    assert all(e == TimeProgEntry.from_str("0", "24:00", "24:00") for e in entries[3:])


def test_build_window_entries_edges():
    entries = tp.build_window_entries(PROGS[0], "00:00", "00:00")
    assert entries[0] == TimeProgEntry.from_str("1", "00:00", "24:00")
    entries = tp.build_window_entries(PROGS[0], "06:00", "24:00")
    assert entries[0] == TimeProgEntry.from_str("0", "00:00", "06:00")
    assert entries[1] == TimeProgEntry.from_str("1", "06:00", "24:00")
    assert entries[2] == TimeProgEntry.from_str("0", "24:00", "24:00")


def test_build_window_entries_invalid():
    with pytest.raises(ValueError):
        tp.build_window_entries(PROGS[0], "15:00", "11:00")
    with pytest.raises(ValueError):
        tp.build_window_entries(PROGS[0], "11:10", "15:00")  # not a 15 minute step
    with pytest.raises(ValueError):
        tp.build_window_entries(PROGS[0], "11:00", "15:00", on_state=2)  # nos=2 -> states 0..1


def test_build_single_entry():
    entry = tp.build_single_entry(PROGS[2], 2, "06:00", "22:00")
    assert entry == TimeProgEntry.from_str("2", "06:00", "22:00")
    with pytest.raises(ValueError):
        tp.build_single_entry(PROGS[0], 2, "06:00", "22:00")


def test_current_entry_skips_unchanged():
    wanted = tp.build_window_entries(PROGS[0], "08:30", "19:00")
    assert all(tp.current_entry(PROGS[0], 0, n) == e for n, e in enumerate(wanted))
    assert tp.current_entry(PROGS[1], 0, 0) is None
