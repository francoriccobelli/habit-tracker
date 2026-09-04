"""Turning habit data into the lines the CLI prints.

Pure string building: every view here takes data and returns ``list[str]``.
Nothing in this module prints, and nothing opens a file -- which is what makes
each view testable as a function rather than through captured stdout.

The layering is one-way and has no cycles::

    storage.py   owns the data file      (never prints)
        ^
    render.py    data -> list[str]       (never prints, never opens a file)
        ^
    cli.py       argparse and dispatch   (prints; opens nothing)

Colour is off until :func:`set_colour` turns it on, so importing this module
never changes what a pipe receives.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from typing import IO

from habit_tracker import storage

# ANSI SGR codes. Only three, deliberately: a completed mark, a de-emphasised
# label, and the prefix on a failure.
_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_DIM = "\033[2m"

#: Column headings, Monday first.
DAY_NAMES = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")

#: Width of the week-label gutter: two spaces plus an ISO date.
_LABEL_WIDTH = len("  2026-08-24")

#: Width of the label column in a stats block.
_STATS_LABEL_WIDTH = 17

_colour_enabled = False


def _enable_windows_vt() -> bool:
    """Switch on ANSI escape processing for a Windows console.

    Windows consoles print escape sequences literally unless
    ``ENABLE_VIRTUAL_TERMINAL_PROCESSING`` is set on the handle. Returns False
    when that cannot be arranged, so the caller leaves colour off rather than
    spraying codes at a console that would show them as text.

    A no-op returning True everywhere else.
    """
    if os.name != "nt":
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_vt = 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
    except Exception:
        # Any surprise here means "no colour", never a traceback.
        return False


def set_colour(mode: str = "auto", stream: IO[str] | None = None) -> None:
    """Decide whether later calls emit ANSI colour.

    Args:
        mode: ``"auto"``, ``"always"`` or ``"never"``. ``auto`` enables colour
            only when ``stream`` is a terminal and ``NO_COLOR`` is unset.
        stream: the stream about to be written to; defaults to stdout.

    ``main()`` calls this on every run, so the setting cannot leak between the
    many invocations a single test process makes -- the same reason
    ``storage.set_data_file`` is called unconditionally.
    """
    global _colour_enabled

    if mode == "never":
        _colour_enabled = False
        return

    if mode == "always":
        # An explicit request wins outright. Still try to put a Windows
        # console into VT mode, but do not make the decision depend on it:
        # when stdout is a pipe or a file there is no console to configure,
        # and the escapes are for whatever consumes them.
        _enable_windows_vt()
        _colour_enabled = True
        return

    # https://no-color.org. An empty value counts as unset, matching how
    # storage treats an empty HABIT_TRACKER_DATA.
    if os.environ.get("NO_COLOR"):
        _colour_enabled = False
        return

    stream = sys.stdout if stream is None else stream
    if not getattr(stream, "isatty", lambda: False)():
        _colour_enabled = False
        return

    # Only here does the VT probe get a veto: on a real console that cannot be
    # switched, escape codes would be printed literally instead of obeyed.
    _colour_enabled = _enable_windows_vt()


def colour_enabled() -> bool:
    """Whether :func:`set_colour` left colour switched on."""
    return _colour_enabled


def _paint(text: str, code: str) -> str:
    """Wrap ``text`` in an SGR code, or return it untouched when colour is off.

    Every colour path goes through here, so with colour disabled the output is
    byte-for-byte what it was before colour existed.
    """
    return f"{code}{text}{_RESET}" if _colour_enabled else text


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """Render ``count`` with the matching form of its noun.

    ``plural(1, "day")`` gives ``"1 day"``; ``plural(2, "day")`` gives
    ``"2 days"``.
    """
    return f"{count} {singular if count == 1 else plural_form or singular + 's'}"


def error(message: str) -> str:
    """The one line every failure takes: a red prefix, then the message."""
    return f"{_paint('error:', _RED)} {message}"


def list_lines(habits: list[storage.Habit], today: date | None = None) -> list[str]:
    """One row per habit: done-today marker, name, and current streak.

    Assumes ``habits`` is non-empty -- an empty tracker gets a sentence from
    the caller, which knows which file it looked in.
    """
    today = today or date.today()
    today_iso = today.isoformat()
    width = max(len(habit["name"]) for habit in habits)

    lines = []
    for habit in habits:
        done_today = today_iso in habit.get("completions", [])
        # The escape codes are zero-width on screen, so colouring the mark
        # does not disturb the column alignment below.
        mark = _paint("x", _GREEN) if done_today else " "

        streak = storage.current_streak(habit, today)
        count = plural(streak, "day")
        lines.append(
            f"[{mark}] {habit['name']:<{width}}  "
            f"{count if streak else _paint(count, _DIM)}"
        )
    return lines


def stats_lines(habit: storage.Habit, today: date | None = None) -> list[str]:
    """A habit's whole record: span, totals, and both streaks."""
    today = today or date.today()
    tracked = storage.tracked_days(habit, today)
    completed = storage.completed_days(habit)
    since = storage.tracked_since(habit, today).isoformat()

    def row(label: str, value: str) -> str:
        # Pad before painting, so the gutter is the same width either way.
        return f"  {_paint(f'{label:<{_STATS_LABEL_WIDTH}}', _DIM)}{value}"

    # tracked_days never returns 0, so the rate cannot divide by zero -- and
    # its window covers every completion, so it cannot exceed 100%. The date
    # comes from that same window, so the two always agree.
    return [
        habit["name"],
        row("Tracking since", f"{since}  ({plural(tracked, 'day')})"),
        row("Completed", f"{plural(completed, 'day')}  ({completed / tracked:.0%})"),
        row("Current streak", plural(storage.current_streak(habit, today), "day")),
        row("Longest streak", plural(storage.longest_streak(habit), "day")),
    ]


def history_lines(
    habit: storage.Habit, today: date | None = None, weeks: int = 4
) -> list[str]:
    """Draw the completion pattern as a Monday-start calendar.

    Three cell states, not two, so the grid never claims a day was missed when
    the habit did not yet exist:

    * ``x`` -- completed;
    * ``.`` -- tracked, not completed;
    * blank -- outside the habit's life: later than ``today``, or earlier than
      the day it started being tracked.

    The window starts at the later of ``weeks`` back and the week the habit
    began, so a habit added yesterday draws one row rather than four empty
    ones.
    """
    today = today or date.today()
    done = {date.fromisoformat(day) for day in habit.get("completions", [])}
    since = storage.tracked_since(habit, today)

    this_monday = today - timedelta(days=today.weekday())
    since_monday = since - timedelta(days=since.weekday())
    start = max(this_monday - timedelta(weeks=weeks - 1), since_monday)

    lines = [
        habit["name"],
        " " * _LABEL_WIDTH + " ".join(f"{name:>2}" for name in DAY_NAMES),
    ]

    tracked = completed = 0
    monday = start
    while monday <= this_monday:
        # Each cell is padded to two columns *before* being painted: escape
        # codes make a string longer without making it wider, so padding a
        # painted cell would be a no-op and the grid would lose its alignment
        # the moment colour was switched on.
        cells = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            if day > today or day < since:
                cells.append("  ")  # outside the habit's life
                continue
            tracked += 1
            if day in done:
                completed += 1
                cells.append(_paint(" x", _GREEN))
            else:
                cells.append(_paint(" .", _DIM))

        label = _paint(f"  {monday.isoformat()}", _DIM)
        lines.append((label + " ".join(cells)).rstrip())
        monday += timedelta(weeks=1)

    lines.append("")
    lines.append(f"  {completed} of {plural(tracked, 'day')}")
    return lines
