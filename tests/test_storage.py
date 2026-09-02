"""Tests for :mod:`habit_tracker.storage`.

Three layers, cheapest first: where the data file lives, that the public
functions exist, and then what they actually do. The behaviour tests all run
against a temporary directory -- see :class:`BehaviourTests`.
"""

import json
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
    """

    def setUp(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
