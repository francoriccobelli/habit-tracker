"""Command-line entry point for habit-tracker.

Everything here is argparse and dispatch -- no file access, no business logic,
and no string building beyond a one-line confirmation. Each ``cmd_*`` handler
takes the parsed namespace and returns a process exit code (0 for success),
which keeps them straightforward to call from tests.

Views come from :mod:`habit_tracker.render`, which returns lines for this
module to print.

Usage::

    habit-tracker add read
    habit-tracker list
    habit-tracker done read
    habit-tracker undone read --date 2026-09-01
    habit-tracker stats read
    habit-tracker history read --weeks 8
    habit-tracker remove read
    habit-tracker --data-file ./demo.json list
    habit-tracker --color never list
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date

from habit_tracker import __version__, render, storage


def _iso_day(raw: str | None) -> str:
    """Normalise an optional ``--date`` to an ISO day, defaulting to today.

    Round-tripping through :class:`date` rejects both "2026-9-2" and
    "not-a-date" here, rather than letting either become a bad entry on disk.

    Raises:
        ValueError: carrying a user-facing message. ``main()`` already renders
            a ValueError as ``error: <message>`` and exits 1, so handlers need
            no try/except of their own.
    """
    if raw is None:
        return date.today().isoformat()

    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(f"{raw!r} is not an ISO date (YYYY-MM-DD)") from None


def _positive_int(raw: str) -> int:
    """An argparse ``type`` for counts that must be at least 1.

    Raising ArgumentTypeError lets argparse render the complaint and exit 2,
    the way it does for every other malformed argument.
    """
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a whole number") from None

    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {value}")
    return value


def cmd_add(args: argparse.Namespace) -> int:
    """Create a new habit to track."""
    habits = storage.load_habits()

    existing = storage.find_habit(habits, args.name)
    if existing is not None:
        # Report the stored spelling, not what was typed -- "Read" and "read"
        # are the same habit, and seeing the stored one explains the refusal.
        print(render.error(f"already tracking {existing['name']!r}"), file=sys.stderr)
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
        # Name the file only when it is not the usual one: an empty tracker is
        # the expected first run at the default path, but at an overridden one
        # it may just mean the path was mistyped.
        where = f" in {storage.data_file()}" if storage.using_override() else ""
        print(f"No habits tracked yet{where}. Add one with: habit-tracker add <name>")
        return 0

    for line in render.list_lines(habits):
        print(line)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show one habit's whole record: how long it has run, totals, streaks.

    Where ``list`` answers "am I on a roll right now?", this answers "how am I
    doing overall?" -- the two genuinely differ once a day has been missed.
    """
    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(render.error(f"not tracking {args.name!r}"), file=sys.stderr)
        return 1

    for line in render.stats_lines(habit):
        print(line)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Draw which days a habit was completed, as a calendar.

    The view `stats` cannot give: a rate says nothing about *why*, while a
    grid whose every gap lands on a weekend says it at a glance.
    """
    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(render.error(f"not tracking {args.name!r}"), file=sys.stderr)
        return 1

    for line in render.history_lines(habit, weeks=args.weeks):
        print(line)
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    """Mark a habit as completed for a given day (default: today)."""
    when = _iso_day(args.date)

    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(render.error(f"not tracking {args.name!r}"), file=sys.stderr)
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


def cmd_undone(args: argparse.Namespace) -> int:
    """Take back one day's completion (default: today).

    The inverse of :func:`cmd_done`, and the only way to correct a mistyped
    ``done`` -- ``remove`` would discard the habit and its whole history.
    """
    when = _iso_day(args.date)

    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(render.error(f"not tracking {args.name!r}"), file=sys.stderr)
        return 1

    completions = habit.get("completions", [])
    if when not in completions:
        # Symmetric with done's already-done case: a no-op, not a failure.
        print(f"{habit['name']!r} was not marked done on {when}.")
        return 0

    # Filter rather than list.remove, which would drop only the first of a
    # repeated day in a hand-edited file.
    habit["completions"] = [day for day in completions if day != when]
    storage.save_habits(habits)
    print(f"Unmarked {habit['name']!r} for {when}.")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Stop tracking a habit and discard its history."""
    habits = storage.load_habits()
    habit = storage.find_habit(habits, args.name)
    if habit is None:
        print(render.error(f"not tracking {args.name!r}"), file=sys.stderr)
        return 1

    habits.remove(habit)
    storage.save_habits(habits)
    lost = storage.completed_days(habit)
    print(
        f"Stopped tracking {habit['name']!r} and "
        f"discarded {render.plural(lost, 'completion')}."
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
    parser.add_argument(
        "--data-file",
        metavar="PATH",
        default=None,
        help=(
            "read and write habits at PATH instead of the default; "
            f"overrides ${storage.DATA_FILE_ENV}"
        ),
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help=(
            "colourise output; 'auto' (the default) means only when writing "
            "to a terminal with $NO_COLOR unset"
        ),
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

    undone = subparsers.add_parser("undone", help="take back a day's completion")
    undone.add_argument("name", help="name of the habit")
    undone.add_argument(
        "--date",
        default=None,
        help="ISO date (YYYY-MM-DD) to un-mark; defaults to today",
    )
    undone.set_defaults(func=cmd_undone)

    remove = subparsers.add_parser("remove", help="stop tracking a habit")
    remove.add_argument("name", help="name of the habit")
    remove.set_defaults(func=cmd_remove)

    stats = subparsers.add_parser("stats", help="show one habit's full record")
    stats.add_argument("name", help="name of the habit")
    stats.set_defaults(func=cmd_stats)

    history = subparsers.add_parser("history", help="draw a habit as a calendar")
    history.add_argument("name", help="name of the habit")
    history.add_argument(
        "--weeks",
        type=_positive_int,
        default=4,
        help="how many weeks to draw (default: 4)",
    )
    history.set_defaults(func=cmd_history)

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

    # Both unconditionally, so that passing no flag *clears* whatever an
    # earlier call left behind rather than inheriting it -- main() runs many
    # times per process under test.
    storage.set_data_file(args.data_file)
    render.set_colour(args.color, sys.stdout)

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
        print(render.error(str(exc)), file=sys.stderr)
        return 1
    except OSError as exc:
        print(render.error(f"could not use the data file: {exc}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
