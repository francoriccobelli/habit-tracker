# habit-tracker

[![CI](https://github.com/francoriccobelli/habit-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/francoriccobelli/habit-tracker/actions/workflows/ci.yml)

A small command-line habit tracker, built while learning Claude Code.

> **Status: working.** All seven commands are implemented and tested against
> a real data file. `list` shows current streaks; `stats` shows one habit's
> full record.

## Requirements

Python 3.10 or newer. No runtime dependencies — argparse, json, and pathlib
from the standard library do the work.

## Install (development)

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # macOS / Linux
pip install -e ".[dev]"
```

That puts a `habit-tracker` command on your PATH. Without installing, the CLI
also runs straight from the source tree:

```bash
python -m habit_tracker.cli --help
```

## Usage

```bash
habit-tracker add read           # start tracking a habit
habit-tracker list               # show habits and current streaks
habit-tracker done read          # mark today complete
habit-tracker done read --date 2026-09-01
habit-tracker undone read        # take back today's completion
habit-tracker stats read         # one habit's full record
habit-tracker history read       # which days you actually did it
habit-tracker remove read        # stop tracking, discard history
```

`undone` is the inverse of `done` and takes the same `--date`. It's how you fix
a mistyped completion — `remove` would throw away the habit and all its history.

`list` answers "am I on a roll right now?"; `stats` answers "how am I doing
overall?" The two differ as soon as a day has been missed:

```
$ habit-tracker list
[x] read  1 day

$ habit-tracker stats read
read
  Tracking since   2026-08-31  (4 days)
  Completed        3 days  (75%)
  Current streak   1 day
  Longest streak   2 days
```

Done today, but yesterday was missed — so the current run is 1 day while the
best run, two days back, was 2.

`history` draws the pattern those numbers summarise. A rate of 72% says
nothing about *why*; a grid whose gaps all fall on the same weekday says it at
a glance:

```
$ habit-tracker history read
read
            Mo Tu We Th Fr Sa Su
  2026-08-17    x  x  .  x  x  .
  2026-08-24 .  x  x  .  x  x  x
  2026-08-31 .  x  x  x  x

  13 of 18 days
```

Rows are weeks starting Monday. `x` is done, `.` is missed, and a blank is a
day outside the habit's life — before you started tracking it, or still in the
future. `--weeks N` widens the window (default 4); it is clamped so a habit
added yesterday draws one row, not four empty ones.

## Colour

Output is coloured when it goes to a terminal and left plain when it is piped
or redirected, so captured output never picks up escape codes. Set
[`NO_COLOR`](https://no-color.org) to turn it off everywhere, or use
`--color auto|always|never` for one run — an explicit `--color always`
overrides `NO_COLOR`.

## Choosing the data file

By default everything lives at `~/.habit_tracker/habits.json`. Two ways to
point somewhere else — useful for a scratch tracker, or for trying the CLI
without touching your real habits:

```bash
habit-tracker --data-file ./demo.json list   # this run only
export HABIT_TRACKER_DATA=./demo.json        # every run in this shell
```

Highest precedence first: `--data-file`, then `HABIT_TRACKER_DATA`, then the
default. `--data-file` is a global option, so it goes *before* the command.

A path that doesn't exist yet is not an error — it starts an empty tracker, and
the file is created on the first `add`. Since a mistyped path would otherwise
look just like an empty tracker, `list` names the file it read whenever the
location has been overridden.

## Data

Habits are stored as JSON at `~/.habit_tracker/habits.json` — outside the
repo, so your own data never lands in a commit. Shape:

```json
{
  "version": 1,
  "habits": [
    { "name": "read", "created": "2026-09-02", "completions": ["2026-09-02"] }
  ]
}
```

## Layout

```
habit_tracker/
  __init__.py    version and package docstring
  cli.py         argparse wiring and command handlers
  render.py      turns habit data into printable lines
  storage.py     the only module that touches the data file
tests/
pyproject.toml
```

The split is deliberate and one-way: `storage.py` never prints, `render.py`
neither prints nor opens a file, and `cli.py` opens nothing — it prints what
`render` returns. Each is testable without the others.

## Tests

```bash
python -m unittest discover -s tests -v   # stdlib, nothing to install
pytest                                    # also works, if you installed [dev]
```

## Roadmap

- [x] Implement `storage.load_habits` / `save_habits` (atomic write)
- [x] Implement the four command handlers
- [x] Streak calculation, shown in `list`
- [x] Real tests for each command
- [x] `stats <name>` — totals, completion rate, and longest streak
- [x] `--data-file` / `HABIT_TRACKER_DATA` override
- [x] `undone <name>` — take back a day's completion
- [x] CI on GitHub Actions (Python 3.10–3.14, plus a Windows job)
- [x] `history <name>` — a Monday-start calendar of completed days
- [x] Colour on a terminal, plain when piped (`--color`, `NO_COLOR`)
- [x] Decide whether concurrent writes need locking — **decided: no.** Writes
      are atomic, but load-modify-save isn't; two overlapping `done` runs can
      lose one. Locking portably is fiddly, and the cost of the rare loss is
      one re-run. Revisit only if the CLI is driven concurrently by a script.

## License

MIT — see [LICENSE](LICENSE).
