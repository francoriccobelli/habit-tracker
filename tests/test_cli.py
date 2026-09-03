"""Tests for the argparse wiring in :mod:`habit_tracker.cli`.

These check the parser, not behaviour -- the command handlers are still stubs.
Behavioural tests arrive with the implementations.
"""

import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
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
        # ``data_file()`` consults --data-file and HABIT_TRACKER_DATA ahead of
        # DATA_FILE, so both are cleared before the redirect below can mean
        # anything. Kept in step with isolate_data_file in test_storage.
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(storage.DATA_FILE_ENV, None)

        storage.set_data_file(None)
        self.addCleanup(storage.set_data_file, None)

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

    def test_stats_requires_a_name(self) -> None:
        args = self.parser.parse_args(["stats", "read"])
        self.assertEqual(args.name, "read")
        self.assertIs(args.func, cli.cmd_stats)

    def test_stats_without_a_name_is_rejected(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.parser.parse_args(["stats"])

    def test_data_file_defaults_to_none(self) -> None:
        self.assertIsNone(self.parser.parse_args(["list"]).data_file)

    def test_data_file_is_accepted_before_the_command(self) -> None:
        args = self.parser.parse_args(["--data-file", "x.json", "list"])
        self.assertEqual(args.data_file, "x.json")
        self.assertIs(args.func, cli.cmd_list)

    def test_data_file_is_not_accepted_after_the_command(self) -> None:
        # A deliberate limitation: it is a global option, like `git --git-dir`.
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.parser.parse_args(["list", "--data-file", "x.json"])

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

    def test_remove_says_one_completion_in_the_singular(self) -> None:
        # Regression: this read "discarded 1 completions" before _plural.
        self.run_cli("add", "read")
        self.run_cli("done", "read", "--date", "2026-09-01")
        _, out, _ = self.run_cli("remove", "read")
        self.assertIn("1 completion.", out)
        self.assertNotIn("1 completions", out)


class PluralTests(unittest.TestCase):
    """The helper behind every count the CLI prints."""

    def test_one_is_singular(self) -> None:
        self.assertEqual(cli._plural(1, "day"), "1 day")

    def test_everything_else_is_plural(self) -> None:
        self.assertEqual(cli._plural(0, "day"), "0 days")
        self.assertEqual(cli._plural(2, "day"), "2 days")

    def test_an_irregular_plural_can_be_given(self) -> None:
        self.assertEqual(cli._plural(2, "entry", "entries"), "2 entries")


class StatsTests(HandlerTestCase):
    def seed(self, created: str, *completions: str) -> None:
        """Write one habit straight to disk, bypassing add/done.

        Lets a test describe an exact history -- including the backdated and
        future shapes the commands would take several calls to build.
        """
        storage.save_habits(
            [{"name": "read", "created": created, "completions": list(completions)}]
        )

    def rate(self, out: str) -> int:
        """Pull the percentage off the Completed line."""
        match = re.search(r"\((\d+)%\)", out)
        self.assertIsNotNone(match, f"no percentage found in:\n{out}")
        return int(match.group(1))

    def test_stats_fails_on_an_unknown_habit(self) -> None:
        code, _, err = self.run_cli("stats", "read")
        self.assertEqual(code, 1)
        self.assertIn("not tracking", err)

    def test_stats_reports_every_field(self) -> None:
        today = date.today().isoformat()
        self.seed(today, today)
        code, out, _ = self.run_cli("stats", "read")
        self.assertEqual(code, 0)
        self.assertIn("read", out)
        self.assertIn(today, out)
        for label in ("Tracking since", "Completed", "Current streak", "Longest streak"):
            with self.subTest(label=label):
                self.assertIn(label, out)

    def test_stats_uses_the_singular_for_one(self) -> None:
        today = date.today().isoformat()
        self.seed(today, today)
        _, out, _ = self.run_cli("stats", "read")
        self.assertIn("1 day", out)
        self.assertNotIn("1 days", out)

    def test_stats_echoes_the_stored_spelling(self) -> None:
        self.run_cli("add", "Read")
        code, out, _ = self.run_cli("stats", "read")
        self.assertEqual(code, 0)
        self.assertIn("Read", out)

    def test_a_backdated_completion_does_not_exceed_full_marks(self) -> None:
        # The real data file's shape: created today, but completed two days
        # ago. A naive completions/(today - created) reads 200% here.
        today = date.today()
        self.seed(today.isoformat(), (today - timedelta(days=2)).isoformat())
        _, out, _ = self.run_cli("stats", "read")
        self.assertLessEqual(self.rate(out), 100)

    def test_the_since_date_matches_the_day_count(self) -> None:
        # Created today but completed two days ago. The header has to read
        # "since <two days ago>  (3 days)" -- pairing the *created* date with
        # a 3-day span would have the line contradict itself.
        today = date.today()
        start = today - timedelta(days=2)
        self.seed(today.isoformat(), start.isoformat())
        _, out, _ = self.run_cli("stats", "read")
        self.assertIn(f"Tracking since   {start.isoformat()}  (3 days)", out)

    def test_a_future_completion_does_not_exceed_full_marks(self) -> None:
        today = date.today()
        self.seed(today.isoformat(), (today + timedelta(days=30)).isoformat())
        _, out, _ = self.run_cli("stats", "read")
        self.assertLessEqual(self.rate(out), 100)

    def test_stats_reports_a_finished_run_as_the_longest(self) -> None:
        # Today, a gap, then three consecutive days: the current streak is 1
        # but the best run was 3. This is what `list` alone cannot show.
        today = date.today()
        days = [(today - timedelta(days=n)).isoformat() for n in (0, 2, 3, 4)]
        self.seed(days[-1], *days)
        _, out, _ = self.run_cli("stats", "read")
        self.assertIn("Current streak   1 day", out)
        self.assertIn("Longest streak   3 days", out)

    def test_stats_leaves_the_data_file_untouched(self) -> None:
        self.run_cli("add", "read")
        before = self.tmp_path.read_bytes()
        self.run_cli("stats", "read")
        self.assertEqual(self.tmp_path.read_bytes(), before)

    def test_stats_reports_a_corrupt_file_without_a_traceback(self) -> None:
        self.tmp_path.parent.mkdir(parents=True)
        self.tmp_path.write_text("{not json", encoding="utf-8")
        code, _, err = self.run_cli("stats", "read")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)


class DataFileFlagTests(HandlerTestCase):
    """End to end through main(), where the flag is actually applied.

    ``self.tmp_path`` is the default location for these tests -- the one the
    base class patched into ``DATA_FILE`` -- so "the default was untouched"
    can be asserted as "that file was never created".
    """

    def setUp(self) -> None:
        super().setUp()
        self.elsewhere = Path(self._tmp.name) / "elsewhere.json"

    def test_the_flag_redirects_reads_and_writes(self) -> None:
        code, _, _ = self.run_cli("--data-file", str(self.elsewhere), "add", "read")
        self.assertEqual(code, 0)
        self.assertTrue(self.elsewhere.is_file())
        self.assertFalse(self.tmp_path.exists())

        _, out, _ = self.run_cli("--data-file", str(self.elsewhere), "list")
        self.assertIn("read", out)

    def test_the_default_path_does_not_see_the_flags_habits(self) -> None:
        self.run_cli("--data-file", str(self.elsewhere), "add", "read")
        _, out, _ = self.run_cli("list")
        self.assertIn("No habits tracked yet", out)

    def test_the_env_var_is_honoured(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = str(self.elsewhere)
        code, _, _ = self.run_cli("add", "read")
        self.assertEqual(code, 0)
        self.assertTrue(self.elsewhere.is_file())
        self.assertFalse(self.tmp_path.exists())

    def test_the_flag_beats_the_env_var(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = str(self.tmp_path)
        self.run_cli("--data-file", str(self.elsewhere), "add", "read")
        self.assertTrue(self.elsewhere.is_file())
        self.assertFalse(self.tmp_path.exists())

    def test_an_override_does_not_leak_into_the_next_run(self) -> None:
        self.run_cli("--data-file", str(self.elsewhere), "add", "read")
        # No flag this time: it must fall back, not reuse the previous path.
        self.run_cli("add", "walk")
        self.assertEqual([h["name"] for h in storage.load_habits()], ["walk"])

    def test_the_empty_message_names_an_overridden_file(self) -> None:
        _, out, _ = self.run_cli("--data-file", str(self.elsewhere), "list")
        self.assertIn("No habits tracked yet in", out)
        self.assertIn(str(self.elsewhere), out)

    def test_the_empty_message_stays_terse_by_default(self) -> None:
        _, out, _ = self.run_cli("list")
        self.assertIn("No habits tracked yet.", out)
        self.assertNotIn(str(self.tmp_path), out)

    def test_a_missing_override_path_starts_an_empty_tracker(self) -> None:
        # The chosen behaviour: a path that does not exist is not an error,
        # because it is the only way to start a tracker somewhere new.
        code, out, err = self.run_cli("--data-file", str(self.elsewhere), "list")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("No habits tracked yet", out)


if __name__ == "__main__":
    unittest.main()
