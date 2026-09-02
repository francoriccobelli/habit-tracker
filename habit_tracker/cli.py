"""Command-line entry point for habit-tracker.

Everything here is argparse and dispatch -- no file access, no business logic.
Each ``cmd_*`` handler takes the parsed namespace and returns a process exit
code (0 for success), which keeps them straightforward to call from tests.

Usage::

    habit-tracker add read
    habit-tracker list
    habit-tracker done read
    habit-tracker remove read
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from habit_tracker import __version__, storage  # noqa: F401  -- TODO: wire up storage


def cmd_add(args: argparse.Namespace) -> int:
    """Create a new habit to track."""
    # TODO: load habits, reject a duplicate name, append
    #       {"name": ..., "created": today, "completions": []}, save.
    print(f"TODO: add habit {args.name!r}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Show every tracked habit and its current streak."""
    # TODO: load habits; print a friendly "no habits yet" line when empty,
    #       otherwise one row per habit with its streak and today's status.
    print("TODO: list habits")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    """Mark a habit as completed for a given day (default: today)."""
    # TODO: load habits, find the habit, append the date to "completions"
    #       (ignoring a repeat for the same day), save.
    print(f"TODO: mark {args.name!r} done for {args.date or 'today'}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Stop tracking a habit and discard its history."""
    # TODO: load habits, drop the match, save. Exit 1 if it was not found.
    print(f"TODO: remove habit {args.name!r}")
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

    # TODO: catch storage errors here and turn them into a tidy message
    #       plus a non-zero exit code, instead of a traceback.
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
