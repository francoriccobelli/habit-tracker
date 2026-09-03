"""Persistence layer for habit data.

All habits live in a single JSON file, by default under the user's home
directory (``~/.habit_tracker/habits.json``). Keeping every read and write in
this module means the CLI never has to know about paths, file locking, or the
on-disk format.

:func:`data_file` resolves the location on every call, so the file can be
redirected three ways -- ``--data-file`` via :func:`set_data_file`, the
:data:`DATA_FILE_ENV` environment variable, or (in tests) patching
:data:`DATA_FILE` itself.

Planned on-disk format (a dict, not a bare list, so we can add fields later
without breaking old files)::

    {
      "version": 1,
      "habits": [
        {
          "name": "read",
          "created": "2026-09-02",
          "completions": ["2026-09-01", "2026-09-02"]
        }
      ]
    }
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

#: Directory holding all habit-tracker state.
DATA_DIR = Path.home() / ".habit_tracker"

#: The single JSON file we read from and write to.
DATA_FILE = DATA_DIR / "habits.json"

#: Environment variable that redirects the data file. Named here so callers
#: and tests refer to it through the module rather than as a bare string.
DATA_FILE_ENV = "HABIT_TRACKER_DATA"

#: Bumped whenever the on-disk shape changes in a way that needs migrating.
SCHEMA_VERSION = 1

Habit = dict[str, Any]
"""One habit record. TODO: promote to a dataclass once the fields settle."""

#: Set by ``--data-file`` through :func:`set_data_file`; outranks the env var.
_override: Path | None = None


def set_data_file(path: str | Path | None) -> None:
    """Point every subsequent read and write at ``path``.

    ``None`` clears the override, restoring the env var or :data:`DATA_FILE`.
    ``main()`` calls this on every run, passing ``None`` when the flag is
    absent, so an override can never outlive the invocation that asked for it.
    """
    global _override
    # expanduser so "~/habits.json" works even where a shell did not expand it.
    _override = Path(path).expanduser() if path is not None else None


def using_override() -> bool:
    """Whether the data file comes from the flag or the environment.

    A statement about the precedence rules, so it belongs beside them rather
    than in ``cli.py`` -- which uses it only to decide whether naming the file
    would tell the user anything they did not already know.
    """
    return _override is not None or bool(os.environ.get(DATA_FILE_ENV))


def data_file() -> Path:
    """Return the path of the JSON file habits are stored in.

    Precedence, highest first: ``--data-file`` (via :func:`set_data_file`),
    then the :data:`DATA_FILE_ENV` environment variable, then
    :data:`DATA_FILE`.

    Every source is read at *call* time rather than import time, which is what
    lets a test redirect :data:`DATA_FILE` in ``setUp`` and have it take
    effect. An empty environment value counts as unset.
    """
    if _override is not None:
        return _override

    from_env = os.environ.get(DATA_FILE_ENV)
    if from_env:
        return Path(from_env).expanduser()

    return DATA_FILE


def ensure_data_dir() -> None:
    """Create the data directory if it does not exist yet.

    Safe to call repeatedly; it is a no-op when the directory is already there.
    """
    data_file().parent.mkdir(parents=True, exist_ok=True)


def load_habits() -> list[Habit]:
    """Read every habit from disk.

    Returns an empty list when the data file does not exist yet, so a fresh
    install behaves exactly like an empty tracker rather than crashing.

    Raises:
        ValueError: if the file exists but does not contain valid JSON in the
            expected shape.
    """
    path = data_file()
    if not path.exists():
        # A fresh install, not an error.
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # JSONDecodeError is already a ValueError, but on its own it says
        # nothing about *which* file is broken.
        raise ValueError(f"{path} does not contain valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"{path} should hold a JSON object, found {type(payload).__name__}"
        )

    version = payload.get("version")
    if not isinstance(version, int):
        raise ValueError(f"{path} has no integer 'version' field")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"{path} was written by a newer habit-tracker (schema {version}, "
            f"this build understands {SCHEMA_VERSION}) -- upgrade to read it"
        )
    # Older schemas would be migrated here; version 1 is still the only one.

    habits = payload.get("habits")
    if not isinstance(habits, list):
        raise ValueError(f"{path} has no 'habits' list")

    return habits


def save_habits(habits: list[Habit]) -> None:
    """Write ``habits`` to disk, replacing whatever was there before.

    Args:
        habits: the complete list of habits. This is a full overwrite, not an
            append -- callers load, mutate, and save the whole collection.
    """
    ensure_data_dir()
    path = data_file()
    payload = {"version": SCHEMA_VERSION, "habits": habits}

    # Write alongside the real file, then swap it in. os.replace is atomic on
    # POSIX and Windows alike, so an interrupted write leaves the previous file
    # intact instead of truncating it. The temp file deliberately shares a
    # directory with the target, so the replace never crosses a filesystem
    # boundary (where it would stop being atomic).
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        # Never leave a stray .tmp behind -- including on Ctrl-C.
        Path(tmp_name).unlink(missing_ok=True)
        raise


def find_habit(habits: list[Habit], name: str) -> Habit | None:
    """Return the habit called ``name``, or ``None`` if there is no such habit.

    Matching is case-insensitive: ``Read`` and ``read`` are the same habit.
    """
    wanted = name.lower()
    return next((h for h in habits if h["name"].lower() == wanted), None)


def current_streak(habit: Habit, today: date | None = None) -> int:
    """Count the run of consecutive days ``habit`` has been completed.

    A streak survives a not-yet-done today: if yesterday was completed but
    today has not been *yet*, the streak still stands, because the day is not
    over. It breaks only once a full day has been missed.

    Args:
        habit: the habit to measure.
        today: the day to count back from. Injectable so tests need not
            freeze the clock.

    Returns:
        The streak length in days; 0 if the habit is not currently on one.
    """
    today = today or date.today()
    done = {date.fromisoformat(d) for d in habit.get("completions", [])}

    cursor = today
    if cursor not in done:
        # Today is still open, so fall back to yesterday before giving up.
        cursor -= timedelta(days=1)
        if cursor not in done:
            return 0

    streak = 0
    while cursor in done:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(habit: Habit) -> int:
    """Measure the longest unbroken run of completed days in the history.

    Unlike :func:`current_streak`, which counts back from today, this looks at
    the whole record -- so it needs no notion of "now" and never shrinks as
    time passes.

    Returns:
        The longest run in days; 0 if the habit has never been completed.
    """
    done = sorted({date.fromisoformat(d) for d in habit.get("completions", [])})
    if not done:
        return 0

    best = run = 1
    for previous, current in zip(done, done[1:]):
        run = run + 1 if current - previous == timedelta(days=1) else 1
        best = max(best, run)
    return best


def completed_days(habit: Habit) -> int:
    """Count the distinct days ``habit`` has been completed.

    Distinct rather than ``len(completions)`` so a hand-edited file that
    repeats a date cannot report more completions than days tracked.
    """
    return len({date.fromisoformat(d) for d in habit.get("completions", [])})


def _window(habit: Habit, today: date) -> tuple[date, date]:
    """The span a habit is measured over, as inclusive ``(start, end)`` dates.

    The window stretches to cover everything rather than simply running from
    ``created`` to today: ``done --date`` accepts any ISO date, so a completion
    can predate the habit (backdating) or fall after today. Spanning both keeps
    every completion inside the window, which is what stops
    ``completed_days / tracked_days`` from exceeding 1.
    """
    done = {date.fromisoformat(d) for d in habit.get("completions", [])}

    created = habit.get("created")
    starts = done | ({date.fromisoformat(created)} if created else set())
    if not starts:
        # No created date and no history -- today is all we can claim.
        return today, today

    start = min(starts)
    # `start` is in the running for `end` too, so a habit somehow created in
    # the future still yields a positive span rather than a negative one.
    return start, max({today, start} | done)


def tracked_since(habit: Habit, today: date | None = None) -> date:
    """The first day ``habit`` is measured from.

    Usually its ``created`` date, but an earlier backdated completion wins --
    otherwise the date would contradict the span :func:`tracked_days` reports.
    """
    return _window(habit, today or date.today())[0]


def tracked_days(habit: Habit, today: date | None = None) -> int:
    """Count the days ``habit`` has been under observation, both ends included.

    Args:
        habit: the habit to measure.
        today: the day the window ends on, unless a later completion pushes it
            out. Injectable so tests need not freeze the clock.

    Returns:
        The window length in days; always at least 1.
    """
    start, end = _window(habit, today or date.today())
    return (end - start).days + 1
