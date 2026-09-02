"""Tests for :mod:`habit_tracker.storage`.

The module is still a skeleton, so what is asserted here is its shape: the
data file lands where we say it does, and the public functions exist. The
skipped tests below spell out the behaviour each stub owes us -- unskip them
as the implementations land.
"""

import unittest
from pathlib import Path

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


@unittest.skip("storage is a skeleton; unskip as each function is implemented")
class BehaviourTests(unittest.TestCase):
    def test_load_returns_empty_list_when_file_is_missing(self) -> None:
        self.assertEqual(storage.load_habits(), [])

    def test_save_then_load_round_trips(self) -> None:
        habits = [{"name": "read", "created": "2026-09-02", "completions": []}]
        storage.save_habits(habits)
        self.assertEqual(storage.load_habits(), habits)

    def test_find_habit_ignores_case(self) -> None:
        habits = [{"name": "Read", "created": "2026-09-02", "completions": []}]
        self.assertIsNotNone(storage.find_habit(habits, "read"))

    def test_find_habit_returns_none_when_absent(self) -> None:
        self.assertIsNone(storage.find_habit([], "read"))


if __name__ == "__main__":
    unittest.main()
