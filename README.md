# habit-tracker

A small command-line habit tracker, built while learning Claude Code.

> **Status: working.** All five commands are implemented and tested against
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
habit-tracker stats read         # one habit's full record
habit-tracker remove read        # stop tracking, discard history
```

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
  storage.py     the only module that touches the data file
tests/
pyproject.toml
```

The split is deliberate: `cli.py` never opens a file, `storage.py` never
prints. Each is testable without the other.

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
- [ ] `--data-file` / `HABIT_TRACKER_DATA` override
- [ ] Decide whether concurrent writes need locking (load-modify-save is racy)

## License

MIT — see [LICENSE](LICENSE).
