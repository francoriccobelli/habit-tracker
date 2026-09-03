"""Tests for :mod:`habit_tracker.storage`.

Three layers, cheapest first: where the data file lives, that the public
functions exist, and then what they actually do. The behaviour tests all run
against a temporary directory -- see :class:`BehaviourTests`.
"""

import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from habit_tracker import storage


def isolate_data_file(test: unittest.TestCase) -> None:
    """Detach ``test`` from any data file the developer's machine points at.

    ``data_file()`` consults ``--data-file`` and ``HABIT_TRACKER_DATA`` before
    ``DATA_FILE``, so redirecting ``DATA_FILE`` alone is no longer enough: on a
    machine where that variable happens to be set, the suite would read and
    write *there* instead of its temp directory. Both are neutralised here, and
    restored on cleanup.
    """
    env = mock.patch.dict(os.environ)
    env.start()
    test.addCleanup(env.stop)
    os.environ.pop(storage.DATA_FILE_ENV, None)

    storage.set_data_file(None)
    test.addCleanup(storage.set_data_file, None)


class DataLocationTests(unittest.TestCase):
    def setUp(self) -> None:
        # This class asserts on the *default* path, so it needs the same
        # detachment even though it never writes.
        isolate_data_file(self)

    def test_data_file_lives_in_a_dotfolder_under_home(self) -> None:
        self.assertEqual(storage.DATA_FILE.parent, storage.DATA_DIR)
        self.assertEqual(storage.DATA_DIR.name, ".habit_tracker")
        self.assertEqual(storage.DATA_DIR.parent, Path.home())

    def test_data_file_is_named_habits_json(self) -> None:
        self.assertEqual(storage.DATA_FILE.name, "habits.json")

    def test_data_file_accessor_agrees_with_the_constant(self) -> None:
        self.assertEqual(storage.data_file(), storage.DATA_FILE)


class PublicSurfaceTests(unittest.TestCase):
    def test_expected_functions_are_callable(self) -> None:
        for name in (
            "ensure_data_dir",
            "load_habits",
            "save_habits",
            "find_habit",
            "current_streak",
            "longest_streak",
            "completed_days",
            "tracked_days",
            "tracked_since",
        ):
            with self.subTest(function=name):
                self.assertTrue(callable(getattr(storage, name)))


class BehaviourTests(unittest.TestCase):
    """What each storage function owes us.

    Every test here runs against a throwaway directory, never the real
    ``~/.habit_tracker``. :func:`storage.data_file` reads the module-level
    ``DATA_FILE`` at call time, so redirecting it in ``setUp`` -- together with
    :func:`isolate_data_file`, which clears the higher-priority flag and env
    var -- keeps the developer's own habits safe from the suite.
    """

    def setUp(self) -> None:
        isolate_data_file(self)

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.tmp_path = Path(self._tmp.name) / ".habit_tracker" / "habits.json"
        patcher = mock.patch.object(storage, "DATA_FILE", self.tmp_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ensure_data_dir_creates_the_directory_and_is_repeatable(self) -> None:
        self.assertFalse(self.tmp_path.parent.exists())
        storage.ensure_data_dir()
        self.assertTrue(self.tmp_path.parent.is_dir())
        storage.ensure_data_dir()  # second call must not raise
        self.assertTrue(self.tmp_path.parent.is_dir())

    def test_find_habit_ignores_case(self) -> None:
        habits = [{"name": "Read", "created": "2026-09-02", "completions": []}]
        self.assertIsNotNone(storage.find_habit(habits, "read"))

    def test_find_habit_returns_none_when_absent(self) -> None:
        self.assertIsNone(storage.find_habit([], "read"))

    def test_load_returns_empty_list_when_file_is_missing(self) -> None:
        self.assertEqual(storage.load_habits(), [])

    def test_load_rejects_a_corrupt_file_with_a_useful_message(self) -> None:
        self.tmp_path.parent.mkdir(parents=True)
        self.tmp_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            storage.load_habits()
        self.assertIn(str(self.tmp_path), str(ctx.exception))

    def test_load_rejects_a_file_from_a_newer_schema(self) -> None:
        self.tmp_path.parent.mkdir(parents=True)
        payload = {"version": storage.SCHEMA_VERSION + 1, "habits": []}
        self.tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            storage.load_habits()

    def test_load_rejects_a_well_formed_file_of_the_wrong_shape(self) -> None:
        self.tmp_path.parent.mkdir(parents=True)
        # Valid JSON, but a bare list rather than the versioned envelope.
        self.tmp_path.write_text('["read"]', encoding="utf-8")
        with self.assertRaises(ValueError):
            storage.load_habits()

    def test_save_then_load_round_trips(self) -> None:
        habits = [{"name": "read", "created": "2026-09-02", "completions": []}]
        storage.save_habits(habits)
        self.assertEqual(storage.load_habits(), habits)

    def test_save_creates_the_data_dir_when_missing(self) -> None:
        self.assertFalse(self.tmp_path.parent.exists())
        storage.save_habits([])
        self.assertTrue(self.tmp_path.is_file())

    def test_save_writes_the_versioned_envelope(self) -> None:
        storage.save_habits([{"name": "read", "created": "x", "completions": []}])
        payload = json.loads(self.tmp_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], storage.SCHEMA_VERSION)
        self.assertEqual(len(payload["habits"]), 1)

    def test_save_leaves_no_temp_files_behind(self) -> None:
        storage.save_habits([])
        strays = [p.name for p in self.tmp_path.parent.iterdir() if p != self.tmp_path]
        self.assertEqual(strays, [])

    def test_save_overwrites_rather_than_appends(self) -> None:
        storage.save_habits([{"name": "read", "created": "x", "completions": []}])
        storage.save_habits([{"name": "walk", "created": "y", "completions": []}])
        habits = storage.load_habits()
        self.assertEqual([h["name"] for h in habits], ["walk"])


class StreakTests(unittest.TestCase):
    """Pure logic, so no temp directory needed -- just an injected 'today'."""

    TODAY = date(2026, 9, 2)

    def habit(self, *offsets: int) -> dict:
        """Build a habit completed ``offsets`` days before TODAY."""
        days = [(self.TODAY - timedelta(days=n)).isoformat() for n in offsets]
        return {"name": "read", "created": "2026-01-01", "completions": days}

    def test_no_completions_is_no_streak(self) -> None:
        self.assertEqual(storage.current_streak(self.habit(), self.TODAY), 0)

    def test_done_today_only(self) -> None:
        self.assertEqual(storage.current_streak(self.habit(0), self.TODAY), 1)

    def test_consecutive_days_accumulate(self) -> None:
        self.assertEqual(storage.current_streak(self.habit(0, 1, 2), self.TODAY), 3)

    def test_streak_survives_a_today_that_is_not_done_yet(self) -> None:
        # Yesterday and the day before, nothing today: the day is not over,
        # so the streak still stands.
        self.assertEqual(storage.current_streak(self.habit(1, 2), self.TODAY), 2)

    def test_a_fully_missed_day_breaks_the_streak(self) -> None:
        # Nothing today or yesterday -- the run is over regardless of history.
        self.assertEqual(storage.current_streak(self.habit(2, 3, 4), self.TODAY), 0)

    def test_only_the_current_run_counts(self) -> None:
        # Today and yesterday, then a gap at day 2, then more history.
        self.assertEqual(storage.current_streak(self.habit(0, 1, 3, 4), self.TODAY), 2)

    def test_completions_need_not_be_sorted(self) -> None:
        self.assertEqual(storage.current_streak(self.habit(2, 0, 1), self.TODAY), 3)


class LongestStreakTests(unittest.TestCase):
    """Also pure logic -- and, unlike current_streak, no 'today' at all."""

    TODAY = date(2026, 9, 2)

    def habit(self, *offsets: int) -> dict:
        """Build a habit completed ``offsets`` days before TODAY."""
        days = [(self.TODAY - timedelta(days=n)).isoformat() for n in offsets]
        return {"name": "read", "created": "2026-01-01", "completions": days}

    def test_no_completions_is_no_streak(self) -> None:
        self.assertEqual(storage.longest_streak(self.habit()), 0)

    def test_a_single_day_is_a_streak_of_one(self) -> None:
        self.assertEqual(storage.longest_streak(self.habit(0)), 1)

    def test_consecutive_days_accumulate(self) -> None:
        self.assertEqual(storage.longest_streak(self.habit(0, 1, 2)), 3)

    def test_a_gap_splits_two_runs(self) -> None:
        # Today, then a gap, then three consecutive days.
        self.assertEqual(storage.longest_streak(self.habit(0, 2, 3, 4)), 3)

    def test_finds_a_past_run_longer_than_the_current_one(self) -> None:
        # The case current_streak cannot see: the best run is over.
        habit = self.habit(0, 2, 3, 4)
        self.assertEqual(storage.current_streak(habit, self.TODAY), 1)
        self.assertEqual(storage.longest_streak(habit), 3)

    def test_completions_need_not_be_sorted(self) -> None:
        self.assertEqual(storage.longest_streak(self.habit(2, 0, 1)), 3)

    def test_repeated_dates_do_not_inflate_the_run(self) -> None:
        habit = {"name": "read", "created": "x", "completions": ["2026-09-01"] * 3}
        self.assertEqual(storage.longest_streak(habit), 1)

    def test_never_shorter_than_the_current_streak(self) -> None:
        for offsets in ((), (0,), (0, 1, 2), (1, 2), (0, 2, 3, 4), (2, 0, 1)):
            with self.subTest(offsets=offsets):
                habit = self.habit(*offsets)
                self.assertGreaterEqual(
                    storage.longest_streak(habit),
                    storage.current_streak(habit, self.TODAY),
                )


class CompletedDaysTests(unittest.TestCase):
    def test_no_completions(self) -> None:
        self.assertEqual(storage.completed_days({"name": "read"}), 0)

    def test_counts_each_day(self) -> None:
        habit = {"completions": ["2026-09-01", "2026-09-02", "2026-09-04"]}
        self.assertEqual(storage.completed_days(habit), 3)

    def test_counts_distinct_days_only(self) -> None:
        habit = {"completions": ["2026-09-01", "2026-09-01", "2026-09-02"]}
        self.assertEqual(storage.completed_days(habit), 2)


class TrackedDaysTests(unittest.TestCase):
    """The window a completion rate is measured against.

    It has to span every completion, because ``done --date`` will happily
    record a day before the habit existed or after today.
    """

    TODAY = date(2026, 9, 3)

    def test_created_today_with_no_history_is_one_day(self) -> None:
        habit = {"created": "2026-09-03", "completions": []}
        self.assertEqual(storage.tracked_days(habit, self.TODAY), 1)

    def test_counts_from_created_inclusive(self) -> None:
        habit = {"created": "2026-09-01", "completions": []}
        self.assertEqual(storage.tracked_days(habit, self.TODAY), 3)

    def test_a_backdated_completion_widens_the_window(self) -> None:
        # Exactly the shape of the real data file: created today, but a
        # completion recorded for two days earlier.
        habit = {"created": "2026-09-03", "completions": ["2026-09-01"]}
        self.assertEqual(storage.tracked_days(habit, self.TODAY), 3)

    def test_a_future_completion_widens_the_window(self) -> None:
        habit = {"created": "2026-09-01", "completions": ["2026-09-05"]}
        self.assertEqual(storage.tracked_days(habit, self.TODAY), 5)

    def test_falls_back_to_the_first_completion_without_created(self) -> None:
        habit = {"completions": ["2026-09-02", "2026-09-03"]}
        self.assertEqual(storage.tracked_days(habit, self.TODAY), 2)

    def test_nothing_at_all_is_still_one_day(self) -> None:
        self.assertEqual(storage.tracked_days({"name": "read"}, self.TODAY), 1)

    def test_never_exceeded_by_the_completed_count(self) -> None:
        # The invariant the rate depends on: it can never read above 100%.
        habits = [
            {"created": "2026-09-03", "completions": ["2026-09-01"]},
            {"created": "2026-09-01", "completions": ["2026-09-05"]},
            {"created": "2026-09-01", "completions": []},
            {"completions": ["2026-09-02", "2026-09-02"]},
        ]
        for habit in habits:
            with self.subTest(habit=habit):
                self.assertLessEqual(
                    storage.completed_days(habit),
                    storage.tracked_days(habit, self.TODAY),
                )


class TrackedSinceTests(unittest.TestCase):
    """The start date must agree with the span tracked_days reports."""

    TODAY = date(2026, 9, 3)

    def test_usually_the_created_date(self) -> None:
        habit = {"created": "2026-09-01", "completions": ["2026-09-02"]}
        self.assertEqual(storage.tracked_since(habit, self.TODAY), date(2026, 9, 1))

    def test_an_earlier_backdated_completion_wins(self) -> None:
        habit = {"created": "2026-09-03", "completions": ["2026-09-01"]}
        self.assertEqual(storage.tracked_since(habit, self.TODAY), date(2026, 9, 1))

    def test_falls_back_to_today_with_nothing_recorded(self) -> None:
        self.assertEqual(storage.tracked_since({}, self.TODAY), self.TODAY)

    def test_the_window_contains_today_and_every_completion(self) -> None:
        # What "Tracking since <date>  (<n> days)" promises the reader: the
        # span really does start on that date and cover everything recorded.
        habits = [
            {"created": "2026-09-03", "completions": ["2026-09-01"]},
            {"created": "2026-09-01", "completions": ["2026-09-05"]},
            {"created": "2026-09-01", "completions": []},
            {"completions": ["2026-09-02"]},
            {},
        ]
        for habit in habits:
            with self.subTest(habit=habit):
                start = storage.tracked_since(habit, self.TODAY)
                end = start + timedelta(days=storage.tracked_days(habit, self.TODAY) - 1)
                self.assertLessEqual(start, self.TODAY)
                self.assertGreaterEqual(end, self.TODAY)
                for iso in habit.get("completions", []):
                    self.assertTrue(start <= date.fromisoformat(iso) <= end)


class DataFileOverrideTests(unittest.TestCase):
    """Precedence: --data-file, then HABIT_TRACKER_DATA, then DATA_FILE."""

    FROM_FLAG = "/tmp/habit-tracker-from-flag.json"
    FROM_ENV = "/tmp/habit-tracker-from-env.json"

    def setUp(self) -> None:
        isolate_data_file(self)

    def test_the_default_is_the_module_constant(self) -> None:
        self.assertEqual(storage.data_file(), storage.DATA_FILE)
        self.assertFalse(storage.using_override())

    def test_the_env_var_is_honoured(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = self.FROM_ENV
        self.assertEqual(storage.data_file(), Path(self.FROM_ENV))
        self.assertTrue(storage.using_override())

    def test_an_empty_env_value_counts_as_unset(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = ""
        self.assertEqual(storage.data_file(), storage.DATA_FILE)
        self.assertFalse(storage.using_override())

    def test_the_flag_outranks_the_env_var(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = self.FROM_ENV
        storage.set_data_file(self.FROM_FLAG)
        self.assertEqual(storage.data_file(), Path(self.FROM_FLAG))

    def test_clearing_the_flag_falls_back_to_the_env_var(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = self.FROM_ENV
        storage.set_data_file(self.FROM_FLAG)
        storage.set_data_file(None)
        self.assertEqual(storage.data_file(), Path(self.FROM_ENV))

    def test_clearing_the_flag_falls_back_to_the_default(self) -> None:
        storage.set_data_file(self.FROM_FLAG)
        storage.set_data_file(None)
        self.assertEqual(storage.data_file(), storage.DATA_FILE)
        self.assertFalse(storage.using_override())

    def test_a_path_object_is_accepted(self) -> None:
        storage.set_data_file(Path(self.FROM_FLAG))
        self.assertEqual(storage.data_file(), Path(self.FROM_FLAG))

    def test_a_tilde_is_expanded_from_the_flag(self) -> None:
        storage.set_data_file("~/habits.json")
        self.assertEqual(storage.data_file(), Path.home() / "habits.json")

    def test_a_tilde_is_expanded_from_the_env_var(self) -> None:
        os.environ[storage.DATA_FILE_ENV] = "~/habits.json"
        self.assertEqual(storage.data_file(), Path.home() / "habits.json")

    def test_reads_and_writes_follow_the_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Nested, to prove ensure_data_dir still makes the parent.
            target = Path(tmp) / "nested" / "habits.json"
            storage.set_data_file(target)
            storage.save_habits([{"name": "read", "created": "x", "completions": []}])

            self.assertTrue(target.is_file())
            self.assertEqual([h["name"] for h in storage.load_habits()], ["read"])


if __name__ == "__main__":
    unittest.main()
