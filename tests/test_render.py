"""Tests for :mod:`habit_tracker.render`.

Every view is a pure function returning ``list[str]``, so nothing here needs a
temp directory or captured stdout -- the lines can simply be asserted on. An
explicit ``today`` is passed throughout so no test depends on the clock.
"""

import io
import os
import unittest
from datetime import date, timedelta
from unittest import mock

from habit_tracker import render

#: A Thursday, so a Monday-start week runs 2026-08-31 .. 2026-09-06.
TODAY = date(2026, 9, 3)

ESCAPE = "\033"


def habit(name: str = "read", created: str = "2026-08-01", *completions: str) -> dict:
    return {"name": name, "created": created, "completions": list(completions)}


def days_before(*offsets: int) -> list[str]:
    """ISO days that many days before :data:`TODAY`."""
    return [(TODAY - timedelta(days=n)).isoformat() for n in offsets]


class ColourOffTestCase(unittest.TestCase):
    """Base for tests that want plain text.

    Colour is module state, so every test sets it deliberately rather than
    inheriting whatever ran before.
    """

    def setUp(self) -> None:
        render.set_colour("never")
        self.addCleanup(render.set_colour, "never")


class PluralTests(ColourOffTestCase):
    """The helper behind every count the CLI prints."""

    def test_one_is_singular(self) -> None:
        self.assertEqual(render.plural(1, "day"), "1 day")

    def test_everything_else_is_plural(self) -> None:
        self.assertEqual(render.plural(0, "day"), "0 days")
        self.assertEqual(render.plural(2, "day"), "2 days")

    def test_an_irregular_plural_can_be_given(self) -> None:
        self.assertEqual(render.plural(2, "entry", "entries"), "2 entries")


class ColourTests(unittest.TestCase):
    """When escapes may be emitted, and -- more importantly -- when they may not."""

    def setUp(self) -> None:
        self.addCleanup(render.set_colour, "never")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("NO_COLOR", None)

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    def test_never_disables_colour(self) -> None:
        render.set_colour("never", self._Tty())
        self.assertFalse(render.colour_enabled())

    def test_always_enables_colour(self) -> None:
        render.set_colour("always")
        self.assertTrue(render.colour_enabled())

    def test_auto_is_off_for_a_non_tty(self) -> None:
        render.set_colour("auto", io.StringIO())
        self.assertFalse(render.colour_enabled())

    def test_auto_is_on_for_a_tty(self) -> None:
        # The VT probe inspects the *real* process stdout, which is a pipe
        # under the test runner. Patch it out: this test is about the auto
        # decision, not about what a particular console can do.
        with mock.patch.object(render, "_enable_windows_vt", return_value=True):
            render.set_colour("auto", self._Tty())
        self.assertTrue(render.colour_enabled())

    def test_a_console_that_cannot_do_vt_gets_no_colour(self) -> None:
        # The other half: escape codes on a console that ignores them would
        # be printed literally, so the probe holds a veto under auto.
        with mock.patch.object(render, "_enable_windows_vt", return_value=False):
            render.set_colour("auto", self._Tty())
        self.assertFalse(render.colour_enabled())

    def test_always_ignores_the_vt_probe(self) -> None:
        # An explicit --color always is not the probe's to overrule: stdout
        # may be a pipe, where there is no console to configure at all.
        with mock.patch.object(render, "_enable_windows_vt", return_value=False):
            render.set_colour("always")
        self.assertTrue(render.colour_enabled())

    def test_no_color_beats_a_tty(self) -> None:
        os.environ["NO_COLOR"] = "1"
        render.set_colour("auto", self._Tty())
        self.assertFalse(render.colour_enabled())

    def test_an_empty_no_color_counts_as_unset(self) -> None:
        # Consistent with how storage treats an empty HABIT_TRACKER_DATA.
        os.environ["NO_COLOR"] = ""
        with mock.patch.object(render, "_enable_windows_vt", return_value=True):
            render.set_colour("auto", self._Tty())
        self.assertTrue(render.colour_enabled())

    def test_error_is_plain_when_colour_is_off(self) -> None:
        render.set_colour("never")
        self.assertEqual(render.error("nope"), "error: nope")

    def test_error_is_painted_when_colour_is_on(self) -> None:
        render.set_colour("always")
        line = render.error("nope")
        self.assertIn(ESCAPE, line)
        self.assertIn("error:", line)
        self.assertTrue(line.endswith("nope"))


class ListLinesTests(ColourOffTestCase):
    def test_one_row_per_habit(self) -> None:
        lines = render.list_lines([habit("read"), habit("walk")], TODAY)
        self.assertEqual(len(lines), 2)

    def test_a_habit_done_today_is_marked(self) -> None:
        done = habit("read", "2026-08-01", TODAY.isoformat())
        self.assertTrue(render.list_lines([done], TODAY)[0].startswith("[x]"))

    def test_an_untouched_habit_is_unmarked(self) -> None:
        self.assertTrue(render.list_lines([habit()], TODAY)[0].startswith("[ ]"))

    def test_names_are_padded_to_the_longest(self) -> None:
        lines = render.list_lines([habit("read"), habit("write a novel")], TODAY)
        # Both streak counts should begin at the same column.
        self.assertEqual(lines[0].index("0 days"), lines[1].index("0 days"))

    def test_the_streak_is_singular_at_one(self) -> None:
        done = habit("read", "2026-08-01", TODAY.isoformat())
        self.assertTrue(render.list_lines([done], TODAY)[0].endswith("1 day"))


class StatsLinesTests(ColourOffTestCase):
    def test_the_name_heads_the_block(self) -> None:
        self.assertEqual(render.stats_lines(habit("read"), TODAY)[0], "read")

    def test_every_label_is_present(self) -> None:
        lines = render.stats_lines(habit(), TODAY)
        joined = "\n".join(lines)
        for label in ("Tracking since", "Completed", "Current streak", "Longest streak"):
            with self.subTest(label=label):
                self.assertIn(label, joined)

    def test_values_all_start_in_the_same_column(self) -> None:
        # Two spaces of gutter, then a 17-wide label column: every value
        # begins at index 19, whatever the label's length.
        for line in render.stats_lines(habit(), TODAY)[1:]:
            with self.subTest(line=line):
                self.assertEqual(line[18], " ", f"label overran: {line!r}")
                self.assertNotEqual(line[19], " ", f"value shifted: {line!r}")

    def test_a_backdated_completion_widens_the_window(self) -> None:
        # Created today but completed two days ago: the window runs from the
        # completion, so the rate is 1 of 3 rather than 1 of 1.
        backdated = habit("read", TODAY.isoformat(), *days_before(2))
        line = next(l for l in render.stats_lines(backdated, TODAY) if "Completed" in l)
        self.assertIn("1 day", line)
        self.assertIn("(33%)", line)


class HistoryLinesTests(ColourOffTestCase):
    """The calendar. TODAY is a Thursday; weeks run Monday to Sunday."""

    def grid(self, hab: dict, weeks: int = 4) -> list[str]:
        """The week rows only -- no name, header, blank line or footer."""
        return render.history_lines(hab, TODAY, weeks)[2:-2]

    def test_the_name_and_weekday_header_come_first(self) -> None:
        lines = render.history_lines(habit(), TODAY, weeks=1)
        self.assertEqual(lines[0], "read")
        self.assertTrue(lines[1].endswith("Mo Tu We Th Fr Sa Su"))

    def test_one_row_per_week(self) -> None:
        old = habit("read", "2026-01-01")
        self.assertEqual(len(self.grid(old, weeks=4)), 4)
        self.assertEqual(len(self.grid(old, weeks=1)), 1)

    def test_rows_are_labelled_with_their_monday(self) -> None:
        rows = self.grid(habit("read", "2026-01-01"), weeks=2)
        self.assertIn("2026-08-24", rows[0])  # the Monday before last
        self.assertIn("2026-08-31", rows[1])  # the Monday of this week

    def test_the_window_is_clamped_to_the_habits_life(self) -> None:
        # Started this week, so four weeks of rows would be three empty ones.
        fresh = habit("read", TODAY.isoformat())
        self.assertEqual(len(self.grid(fresh, weeks=4)), 1)

    def test_completed_days_are_marked(self) -> None:
        # Monday and Wednesday of this week.
        hab = habit("read", "2026-08-31", "2026-08-31", "2026-09-02")
        row = self.grid(hab, weeks=1)[0]
        self.assertTrue(row.endswith("x  .  x  ."), f"unexpected row: {row!r}")

    def test_days_after_today_are_blank_not_missed(self) -> None:
        # TODAY is Thursday, so Friday-Sunday must not read as failures.
        row = self.grid(habit("read", "2026-08-31"), weeks=1)[0]
        self.assertEqual(row.count("."), 4, f"unexpected row: {row!r}")

    def test_days_before_the_habit_existed_are_blank(self) -> None:
        # Created Wednesday: Monday and Tuesday are not the habit's failures.
        row = self.grid(habit("read", "2026-09-02"), weeks=1)[0]
        self.assertEqual(row.count("."), 2, f"unexpected row: {row!r}")

    def test_the_footer_counts_only_days_on_screen(self) -> None:
        hab = habit("read", "2026-08-31", "2026-08-31", "2026-09-02")
        self.assertEqual(render.history_lines(hab, TODAY, 1)[-1], "  2 of 4 days")

    def test_a_single_day_is_singular_in_the_footer(self) -> None:
        hab = habit("read", TODAY.isoformat(), TODAY.isoformat())
        self.assertEqual(render.history_lines(hab, TODAY, 1)[-1], "  1 of 1 day")


class HistoryAlignmentTests(unittest.TestCase):
    """Colour must not disturb the grid: escapes are long but zero-width."""

    def setUp(self) -> None:
        self.addCleanup(render.set_colour, "never")

    @staticmethod
    def _visible(text: str) -> str:
        """Strip SGR sequences, leaving what the terminal actually shows."""
        out, i = [], 0
        while i < len(text):
            if text[i] == ESCAPE:
                i = text.index("m", i) + 1
                continue
            out.append(text[i])
            i += 1
        return "".join(out)

    def test_the_visible_grid_is_identical_with_and_without_colour(self) -> None:
        hab = habit("read", "2026-08-17", *days_before(0, 2, 3, 8, 9))

        render.set_colour("never")
        plain = render.history_lines(hab, TODAY, weeks=3)

        render.set_colour("always")
        painted = render.history_lines(hab, TODAY, weeks=3)

        self.assertNotEqual(plain, painted, "colour should have changed the bytes")
        self.assertEqual(plain, [self._visible(line) for line in painted])

    def test_the_visible_list_is_identical_with_and_without_colour(self) -> None:
        habits = [
            habit("read", "2026-08-01", TODAY.isoformat()),
            habit("write a novel", "2026-08-01"),
        ]

        render.set_colour("never")
        plain = render.list_lines(habits, TODAY)

        render.set_colour("always")
        painted = render.list_lines(habits, TODAY)

        self.assertEqual(plain, [self._visible(line) for line in painted])

    def test_the_visible_stats_block_is_identical_with_and_without_colour(self) -> None:
        hab = habit("read", "2026-08-01", *days_before(0, 1))

        render.set_colour("never")
        plain = render.stats_lines(hab, TODAY)

        render.set_colour("always")
        painted = render.stats_lines(hab, TODAY)

        self.assertEqual(plain, [self._visible(line) for line in painted])


if __name__ == "__main__":
    unittest.main()
