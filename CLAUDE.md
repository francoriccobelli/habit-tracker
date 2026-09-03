# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

All five commands (`add`, `list`, `done`, `remove`, `stats`) work end to end
and are tested. What remains is in the README's Roadmap section, which should
be updated as items land — chiefly the `--data-file` / `HABIT_TRACKER_DATA`
override, and a decision on whether concurrent writes need locking.

**Known limitation:** `save_habits` is atomic, but the load-modify-save cycle
in each handler is not. Two `habit-tracker done` runs racing each other can
still lose a write. Deliberately unaddressed — see the roadmap.

## Commands

```bash
python -m unittest discover -s tests -v          # full suite, stdlib only
python -m unittest discover -s tests -k <name>   # single test by name
python -m pytest                                 # also works; needs [dev]
python -m habit_tracker.cli --help               # run without installing
pip install -e ".[dev]"                          # puts `habit-tracker` on PATH
```

`-s tests` matters: `tests/` has no `__init__.py`, so adding `-t .` breaks
discovery with "Start directory is not importable".

## Architecture

Two modules with a strict, enforced split:

- **`cli.py` never opens a file.** Argparse setup and dispatch only.
- **`storage.py` never prints.** It is the sole owner of the data file — its
  path, its format, and its migrations.

This is what makes each module testable without the other, and it is the one
rule to preserve when adding features. A new command that needs data asks
`storage` for it; it does not reach for `pathlib` itself.

Conventions that follow from that split:

- **Handlers return exit codes.** Each `cmd_*` takes the parsed namespace and
  returns an `int` (0 = success) rather than calling `sys.exit`. Tests call
  them directly and assert on the return value.
- **Errors go to stderr, results to stdout.** `main()` is the single place
  that converts a `ValueError` (corrupt data file) or `OSError` (permissions,
  disk) into a one-line message and exit 1, so no handler needs its own
  try/except and no user sees a traceback.
- **Pure logic lives in `storage.py`, not `cli.py`.** `find_habit`,
  `current_streak`, `longest_streak`, `completed_days`, `tracked_days` and
  `tracked_since` take data and return data — they touch neither the disk nor
  stdout. They sit in
  `storage.py` because `cli.py` is explicitly barred from holding business
  logic. Put the next such helper there too. The exception is *formatting*:
  `_plural` lives in `cli.py`, because `storage.py` never prints.
- **`build_parser()` is split out from `main()`** so tests can inspect the
  parser and check `--help` without running a command.
- **`data_file()` is indirection on purpose.** Nothing hard-codes `DATA_FILE`;
  the accessor is the future home of a `HABIT_TRACKER_DATA` env var and a
  `--data-file` flag.

## Testing: the one rule

**Any test that reaches storage must redirect `storage.DATA_FILE` to a temp
directory first.** `data_file()` reads that module global at call time, so
`mock.patch.object(storage, "DATA_FILE", tmp)` in `setUp` is enough.

This is not stylistic. `save_habits` writes for real, so a test without the
redirect writes to the developer's own `~/.habit_tracker/habits.json`. Both
suites have a base for this: `BehaviourTests.setUp` in `tests/test_storage.py`
and `HandlerTestCase` in `tests/test_cli.py` (which also gives you `run_cli()`,
returning `(exit_code, stdout, stderr)`). Inherit one rather than rolling your
own.

## Data format

One JSON file at `~/.habit_tracker/habits.json` — outside the repo, so user
data cannot land in a commit. The payload is a dict, not a bare list, so fields
can be added later without breaking old files:

```json
{ "version": 1, "habits": [{ "name": "read", "created": "...", "completions": ["..."] }] }
```

Bump `SCHEMA_VERSION` whenever the on-disk shape changes in a way that needs
migrating.

## Dependencies

Zero runtime dependencies, on purpose — argparse, json, and pathlib cover the
whole problem. `pyproject.toml` says to add one only when it "really earns its
place." Reach for the standard library first. Requires Python 3.10+ (the code
uses `X | None` annotations and `from __future__ import annotations`).

## Writing a new command

1. Add a subparser in `build_parser()` and a `cmd_*` handler beside the others.
2. The handler loads via `storage`, mutates the list, saves the whole list
   back — `save_habits` is a full overwrite, not an append.
3. Let storage exceptions propagate; `main()` already renders them.
4. Test it against `HandlerTestCase`, asserting on the exit code and on what
   landed on disk, not only on printed output.

Habit names match case-insensitively everywhere, and messages echo the
*stored* spelling rather than what the user typed — so `add Read` then
`done read` reports "Read".
