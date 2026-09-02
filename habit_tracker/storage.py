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

import json  # noqa: F401  -- TODO: used once load/save are implemented
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
    # TODO: data_file().parent.mkdir(parents=True, exist_ok=True)
    raise NotImplementedError("storage.ensure_data_dir is not implemented yet")


def load_habits() -> list[Habit]:
    """Read every habit from disk.

    Returns an empty list when the data file does not exist yet, so a fresh
    install behaves exactly like an empty tracker rather than crashing.

    Raises:
        ValueError: if the file exists but does not contain valid JSON in the
            expected shape.
    """
    # TODO:
    #   1. If data_file() is missing, return [].
    #   2. json.loads(data_file().read_text(encoding="utf-8")).
    #   3. Validate "version" and hand off to a migration if it is older.
    #   4. Return payload["habits"].
    raise NotImplementedError("storage.load_habits is not implemented yet")


def save_habits(habits: list[Habit]) -> None:
    """Write ``habits`` to disk, replacing whatever was there before.

    Args:
        habits: the complete list of habits. This is a full overwrite, not an
            append -- callers load, mutate, and save the whole collection.
    """
    # TODO:
    #   1. ensure_data_dir().
    #   2. Dump {"version": SCHEMA_VERSION, "habits": habits} with indent=2.
    #   3. Write to a temp file in the same directory, then os.replace() onto
    #      data_file() so an interrupted write cannot truncate good data.
    raise NotImplementedError("storage.save_habits is not implemented yet")


def find_habit(habits: list[Habit], name: str) -> Habit | None:
    """Return the habit called ``name``, or ``None`` if there is no such habit.

    Matching is case-insensitive: ``Read`` and ``read`` are the same habit.
    """
    # TODO: next((h for h in habits if h["name"].lower() == name.lower()), None)
    raise NotImplementedError("storage.find_habit is not implemented yet")
