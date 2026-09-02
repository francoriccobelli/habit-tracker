"""Persistence layer for habit data.

All habits live in a single JSON file under the user's home directory
(``~/.habit_tracker/habits.json``). Keeping every read and write in this module
means the CLI never has to know about paths, file locking, or the on-disk
format -- and it makes the whole thing easy to test by pointing
:data:`DATA_DIR` somewhere temporary.

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
from pathlib import Path
from typing import Any

#: Directory holding all habit-tracker state.
DATA_DIR = Path.home() / ".habit_tracker"

#: The single JSON file we read from and write to.
DATA_FILE = DATA_DIR / "habits.json"

#: Bumped whenever the on-disk shape changes in a way that needs migrating.
SCHEMA_VERSION = 1

Habit = dict[str, Any]
"""One habit record. TODO: promote to a dataclass once the fields settle."""


def data_file() -> Path:
    """Return the path of the JSON file habits are stored in.

    Indirection on purpose: tests (and, later, a ``--data-file`` flag) can
    override the location without every caller hard-coding :data:`DATA_FILE`.
    """
    # TODO: honour a HABIT_TRACKER_DATA env var, then fall back to DATA_FILE.
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
