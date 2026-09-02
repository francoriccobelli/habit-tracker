"""Tests for the argparse wiring in :mod:`habit_tracker.cli`.

These check the parser, not behaviour -- the command handlers are still stubs.
Behavioural tests arrive with the implementations.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from habit_tracker import cli, storage


class HandlerTestCase(unittest.TestCase):
    """Base for tests that run a real command against a throwaway data file.

    The handlers write, so -- exactly as in test_storage -- every test here
    redirects ``storage.DATA_FILE`` into a temporary directory. Nothing in
    this suite may touch the developer's own ``~/.habit_tracker``.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.tmp_path = Path(self._tmp.name) / ".habit_tracker" / "habits.json"
        patcher = mock.patch.object(storage, "DATA_FILE", self.tmp_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        """Run ``argv`` through :func:`cli.main`, capturing both streams."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()


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


class AddTests(HandlerTestCase):
    def test_add_persists_a_new_habit(self) -> None:
        code, out, _ = self.run_cli("add", "read")
        self.assertEqual(code, 0)
        self.assertIn("read", out)

        habits = storage.load_habits()
        self.assertEqual([h["name"] for h in habits], ["read"])
        self.assertEqual(habits[0]["completions"], [])
        self.assertTrue(habits[0]["created"])

    def test_add_rejects_a_duplicate_regardless_of_case(self) -> None:
        self.run_cli("add", "Read")
        code, _, err = self.run_cli("add", "read")
        self.assertEqual(code, 1)
        self.assertIn("Read", err)  # echoes the stored spelling
        self.assertEqual(len(storage.load_habits()), 1)

    def test_add_keeps_existing_habits(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("add", "walk")
        self.assertEqual([h["name"] for h in storage.load_habits()], ["read", "walk"])


class ListTests(HandlerTestCase):
    def test_list_is_friendly_when_there_is_nothing_yet(self) -> None:
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("No habits tracked yet", out)

    def test_list_shows_one_row_per_habit(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("add", "walk")
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 2)
        self.assertIn("read", out)
        self.assertIn("walk", out)

    def test_list_marks_a_habit_done_today(self) -> None:
        # Seeded through storage rather than the `done` command, so this tests
        # only how `list` renders state.
        today = date.today().isoformat()
        storage.save_habits(
            [{"name": "read", "created": today, "completions": [today]}]
        )
        _, out, _ = self.run_cli("list")
        self.assertIn("[x]", out)
        self.assertIn("1 day", out)  # singular, not "1 days"

    def test_list_leaves_an_untouched_habit_unmarked(self) -> None:
        self.run_cli("add", "read")
        _, out, _ = self.run_cli("list")
        self.assertIn("[ ]", out)
        self.assertNotIn("[x]", out)

    def test_list_reports_a_corrupt_file_without_a_traceback(self) -> None:
        self.tmp_path.parent.mkdir(parents=True)
        self.tmp_path.write_text("{not json", encoding="utf-8")
        code, _, err = self.run_cli("list")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)


class DoneTests(HandlerTestCase):
    def test_done_records_today_by_default(self) -> None:
        self.run_cli("add", "read")
        code, out, _ = self.run_cli("done", "read")
        self.assertEqual(code, 0)
        self.assertIn("read", out)

        habit = storage.load_habits()[0]
        self.assertEqual(habit["completions"], [date.today().isoformat()])

    def test_done_accepts_an_explicit_date(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("done", "read", "--date", "2026-09-01")
        self.assertEqual(storage.load_habits()[0]["completions"], ["2026-09-01"])

    def test_done_twice_on_one_day_does_not_duplicate(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("done", "read", "--date", "2026-09-01")
        code, out, _ = self.run_cli("done", "read", "--date", "2026-09-01")
        self.assertEqual(code, 0)  # a no-op, not a failure
        self.assertIn("already done", out)
        self.assertEqual(storage.load_habits()[0]["completions"], ["2026-09-01"])

    def test_done_keeps_completions_sorted(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("done", "read", "--date", "2026-09-03")
        self.run_cli("done", "read", "--date", "2026-09-01")
        self.assertEqual(
            storage.load_habits()[0]["completions"],
            ["2026-09-01", "2026-09-03"],
        )

    def test_done_rejects_an_unparseable_date(self) -> None:
        self.run_cli("add", "read")
        code, _, err = self.run_cli("done", "read", "--date", "yesterday")
        self.assertEqual(code, 1)
        self.assertIn("ISO date", err)
        self.assertEqual(storage.load_habits()[0]["completions"], [])

    def test_done_fails_on_an_unknown_habit(self) -> None:
        code, _, err = self.run_cli("done", "read")
        self.assertEqual(code, 1)
        self.assertIn("not tracking", err)

    def test_done_matches_case_insensitively(self) -> None:
        self.run_cli("add", "Read")
        code, _, _ = self.run_cli("done", "read")
        self.assertEqual(code, 0)
        self.assertEqual(len(storage.load_habits()[0]["completions"]), 1)


class RemoveTests(HandlerTestCase):
    def test_remove_drops_the_habit(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("add", "walk")
        code, out, _ = self.run_cli("remove", "read")
        self.assertEqual(code, 0)
        self.assertIn("read", out)
        self.assertEqual([h["name"] for h in storage.load_habits()], ["walk"])

    def test_remove_says_how_much_history_was_discarded(self) -> None:
        self.run_cli("add", "read")
        self.run_cli("done", "read", "--date", "2026-09-01")
        self.run_cli("done", "read", "--date", "2026-09-02")
        _, out, _ = self.run_cli("remove", "read")
        self.assertIn("2 completions", out)

    def test_remove_fails_on_an_unknown_habit(self) -> None:
        code, _, err = self.run_cli("remove", "read")
        self.assertEqual(code, 1)
        self.assertIn("not tracking", err)

    def test_remove_matches_case_insensitively(self) -> None:
        self.run_cli("add", "Read")
        code, _, _ = self.run_cli("remove", "read")
        self.assertEqual(code, 0)
        self.assertEqual(storage.load_habits(), [])


if __name__ == "__main__":
    unittest.main()
