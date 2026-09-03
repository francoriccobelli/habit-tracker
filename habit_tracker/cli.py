"""Command-line entry point for habit-tracker.

Everything here is argparse and dispatch -- no file access, no business logic.
Each ``cmd_*`` handler takes the parsed namespace and returns a process exit
code (0 for success), which keeps them straightforward to call from tests.

Usage::

    habit-tracker add read
    habit-tracker list
    habit-tracker done read
    habit-tracker stats read
    habit-tracker remove read
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date

from habit_tracker import __version__, storage


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """Render ``count`` with the matching form of its noun.

    ``_plural(1, "day")`` gives ``"1 day"``, ``_plural(2, "day")`` gives
    ``"2 days"``. Formatting, so it lives here rather than in storage -- which
    never prints.
    """
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def cmd_add(args: argparse.Namespace) -> int:
    """Create a new habit to track."""
    habits = storage.load_habits()

    existing = storage.find_habit(habits, args.name)
    if existing is not None:
        # Report the stored spelling, not what was typed -- "Read" and "read"
        # are the same habit, and seeing the stored one explains the refusal.
        print(f"error: already tracking {existing['name']!r}", file=sys.stderr)
        return 1

    habits.append(
        {
            "name": args.name,
            "created": date.today().isoformat(),
            "completions": [],
        }
    )
    storage.save_habits(habits)
    print(f"Tracking {args.name!r}.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Show every tracked habit and its current streak."""
    habits = storage.load_habits()
    if not habits:
        print("No habits tracked yet. Add one with: habit-tracker add <name>")
        return 0

    today = date.today()
    today_iso = today.isoformat()
    width = max(len(h["name"]) for h in habits)

    for habit in habits:
        mark = "x" if today_iso in habit.get("completions", []) else " "
        streak = storage.current_streak(habit, today)
        print(f"[{mark}] {habit['name']:<{width}}  {_plural(streak, 'day')}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show one habit's whole record: how long it has run, totals, streaks.

    Where ``list`` answers "am I on a roll right now?", this answers "how am I
    doing overall?" -- the two genuinely differ once a day has been missed.
    """
    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(f"error: not tracking {args.name!r}", file=sys.stderr)
        return 1

    today = date.today()
    tracked = storage.tracked_days(habit, today)
    completed = storage.completed_days(habit)

    # tracked_days never returns 0, so the rate cannot divide by zero -- and
    # its window covers every completion, so it cannot exceed 100%. The date
    # comes from the same window as the count, so the two always agree.
    print(habit["name"])
    print(
        f"  Tracking since   {storage.tracked_since(habit, today).isoformat()}"
        f"  ({_plural(tracked, 'day')})"
    )
    print(f"  Completed        {_plural(completed, 'day')}  ({completed / tracked:.0%})")
    print(f"  Current streak   {_plural(storage.current_streak(habit, today), 'day')}")
    print(f"  Longest streak   {_plural(storage.longest_streak(habit), 'day')}")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    """Mark a habit as completed for a given day (default: today)."""
    if args.date is None:
        when = date.today().isoformat()
    else:
        try:
            # Round-trip through date so "2026-9-2" and "not-a-date" are both
            # rejected here, rather than becoming a bad entry on disk.
            when = date.fromisoformat(args.date).isoformat()
        except ValueError:
            print(
                f"error: {args.date!r} is not an ISO date (YYYY-MM-DD)",
                file=sys.stderr,
            )
            return 1

    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(f"error: not tracking {args.name!r}", file=sys.stderr)
        return 1

    completions = habit.setdefault("completions", [])
    if when in completions:
        # Marking the same day twice is a no-op, not a failure.
        print(f"{habit['name']!r} was already done on {when}.")
        return 0

    completions.append(when)
    completions.sort()  # keep the file readable when days arrive out of order
    storage.save_habits(habits)
    print(f"Marked {habit['name']!r} done for {when}.")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Stop tracking a habit and discard its history."""
    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(f"error: not tracking {args.name!r}", file=sys.stderr)
        return 1

    habits.remove(habit)
    storage.save_habits(habits)
    lost = storage.completed_days(habit)
    print(
        f"Stopped tracking {habit['name']!r} and "
        f"discarded {_plural(lost, 'completion')}."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and its subcommands.

    Split out from :func:`main` so tests can inspect the parser -- and so
    ``--help`` output can be checked without running a command.
    """
    parser = argparse.ArgumentParser(
        prog="habit-tracker",
        description="Track daily habits from the command line.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    add = subparsers.add_parser("add", help="start tracking a new habit")
    add.add_argument("name", help="name of the habit, e.g. 'read'")
    add.set_defaults(func=cmd_add)

    listing = subparsers.add_parser("list", help="show all tracked habits")
    listing.set_defaults(func=cmd_list)

    done = subparsers.add_parser("done", help="mark a habit complete for a day")
    done.add_argument("name", help="name of the habit")
    done.add_argument(
        "--date",
        default=None,
        help="ISO date (YYYY-MM-DD) to mark complete; defaults to today",
    )
    done.set_defaults(func=cmd_done)

    remove = subparsers.add_parser("remove", help="stop tracking a habit")
    remove.add_argument("name", help="name of the habit")
    remove.set_defaults(func=cmd_remove)

    stats = subparsers.add_parser("stats", help="show one habit's full record")
    stats.add_argument("name", help="name of the habit")
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and run the matching command.

    Args:
        argv: arguments to parse. ``None`` means read from ``sys.argv``.

    Returns:
        The process exit code: 0 on success, non-zero on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        # No subcommand given -- show help rather than doing nothing silently.
        parser.print_help()
        return 1

    # One place to turn a storage failure into a tidy message. ValueError is
    # a corrupt or unreadable data file; OSError is a permissions or disk
    # problem. Either way the user gets a line, not a traceback.
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: could not use the data file: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
