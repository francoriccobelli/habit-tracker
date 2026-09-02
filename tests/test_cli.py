"""Tests for the argparse wiring in :mod:`habit_tracker.cli`.

These check the parser, not behaviour -- the command handlers are still stubs.
Behavioural tests arrive with the implementations.
"""

import io
import unittest
from contextlib import redirect_stdout

from habit_tracker import cli


class BuildParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = cli.build_parser()

    def test_add_requires_a_name(self) -> None:
        args = self.parser.parse_args(["add", "read"])
        self.assertEqual(args.name, "read")
        self.assertIs(args.func, cli.cmd_add)

    def test_list_takes_no_arguments(self) -> None:
        args = self.parser.parse_args(["list"])
        self.assertIs(args.func, cli.cmd_list)

    def test_done_defaults_to_no_explicit_date(self) -> None:
        args = self.parser.parse_args(["done", "read"])
        self.assertIsNone(args.date)
        self.assertIs(args.func, cli.cmd_done)

    def test_done_accepts_an_explicit_date(self) -> None:
        args = self.parser.parse_args(["done", "read", "--date", "2026-09-01"])
        self.assertEqual(args.date, "2026-09-01")

    def test_remove_requires_a_name(self) -> None:
        args = self.parser.parse_args(["remove", "read"])
        self.assertEqual(args.name, "read")
        self.assertIs(args.func, cli.cmd_remove)

    def test_unknown_command_exits(self) -> None:
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            self.parser.parse_args(["polish-shoes"])


class MainTests(unittest.TestCase):
    def test_no_command_prints_help_and_fails(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = cli.main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("usage: habit-tracker", out.getvalue())

    def test_version_flag_exits_cleanly(self) -> None:
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(io.StringIO()):
            cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
