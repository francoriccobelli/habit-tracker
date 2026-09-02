"""Tests for :mod:`habit_tracker.storage`.

The module is still a skeleton, so what is asserted here is its shape: the
data file lands where we say it does, and the public functions exist. The
skipped tests below spell out the behaviour each stub owes us -- unskip them
as the implementations land.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from habit_tracker import storage


class DataLocationTests(unittest.TestCase):
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
        for name in ("ensure_data_dir", "load_habits", "save_habits", "find_habit"):
            with self.subTest(function=name):
                self.assertTrue(callable(getattr(storage, name)))


class BehaviourTests(unittest.TestCase):
    """What each storage function owes us.

    Every test here runs against a throwaway directory, never the real
    ``~/.habit_tracker``. :func:`storage.data_file` reads the module-level
    ``DATA_FILE`` at call time, so redirecting it in ``setUp`` is enough to
    keep the developer's own habits safe from the suite.

    The skips are per-test rather than on the class so each one can be turned
    on as its function lands, instead of all four arriving at once.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.tmp_path = Path(self._tmp.name) / ".habit_tracker" / "habits.json"
        patcher = mock.patch.object(storage, "DATA_FILE", self.tmp_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    @unittest.skip("unskip when storage.load_habits is implemented")
    def test_load_returns_empty_list_when_file_is_missing(self) -> None:
        self.assertEqual(storage.load_habits(), [])

    @unittest.skip("unskip when storage.save_habits is implemented")
    def test_save_then_load_round_trips(self) -> None:
        habits = [{"name": "read", "created": "2026-09-02", "completions": []}]
        storage.save_habits(habits)
        self.assertEqual(storage.load_habits(), habits)

    @unittest.skip("unskip when storage.find_habit is implemented")
    def test_find_habit_ignores_case(self) -> None:
        habits = [{"name": "Read", "created": "2026-09-02", "completions": []}]
        self.assertIsNotNone(storage.find_habit(habits, "read"))

    @unittest.skip("unskip when storage.find_habit is implemented")
    def test_find_habit_returns_none_when_absent(self) -> None:
        self.assertIsNone(storage.find_habit([], "read"))


if __name__ == "__main__":
    unittest.main()
