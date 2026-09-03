# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

All six commands (`add`, `list`, `done`, `undone`, `remove`, `stats`) work end
to end and are tested, and the data file can be redirected with `--data-file`
or `HABIT_TRACKER_DATA`. Every roadmap item in the README is now closed. New
work should add an item there and tick it as it lands.

CI lives in `.github/workflows/ci.yml` (Python 3.10–3.14 on Ubuntu, plus a
Windows job). It runs the suite twice — once with nothing installed, to keep
the stdlib-only promise honest — and re-runs it with `HABIT_TRACKER_DATA` set,
failing if the suite writes to that path. **Note:** as of this writing the
workflow has never actually run; `origin/main` is behind and nothing has been
pushed.

**Known limitation, accepted and closed: no write locking.** `save_habits` is
atomic — it writes a temp file and `os.replace`s it, so an interrupted write
never truncates the real one — but the load-modify-save cycle in each handler
is not. Two `habit-tracker done` runs overlapping within the same few
milliseconds can still lose one write.

This was considered and deliberately rejected, not overlooked. The race needs
two processes writing at genuinely the same instant, which typing commands by
hand does not produce; cross-platform advisory locking is fiddly (no portable
`fcntl`, and lock files need stale-lock recovery); and the cost of the rare
loss is one re-run of `done`. **Do not add locking without a concrete reason**
— if one appears, it will be because the CLI is being driven concurrently by a
script or a cron job, and *that* is the change that should reopen this.

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
  logic. Put the next such helper there too. The exceptions are the two ends of
  the CLI's own I/O: `_plural` (formatting) and `_iso_day` (parsing `--date`)
  live in `cli.py`, because `storage.py` neither prints nor reads argv.
  `_iso_day` raises `ValueError` with a user-facing message rather than
  printing, letting `main()`'s existing handler render it.
- **`build_parser()` is split out from `main()`** so tests can inspect the
  parser and check `--help` without running a command.
- **`data_file()` is indirection on purpose.** Nothing hard-codes `DATA_FILE`.
  The accessor resolves the path on every call, highest precedence first:
  `--data-file` (stored by `set_data_file()`, which `main()` calls on every run
  so an override cannot outlive it), then `HABIT_TRACKER_DATA`, then
  `DATA_FILE`. Resolution at *call* time is what lets tests redirect the
  constant. `using_override()` reports whether the path came from either
  override — `cmd_list` uses it to decide whether naming the file is useful.

## Testing: the one rule

**Any test that reaches storage must detach from the real data file first** —
and that now takes two steps, not one:

1. Redirect the constant: `mock.patch.object(storage, "DATA_FILE", tmp)`.
2. Clear what outranks it — the `HABIT_TRACKER_DATA` env var and any
   `set_data_file()` override. Step 1 alone is **not** enough: both are
   consulted ahead of `DATA_FILE`, so on a machine where that variable happens
   to be set, a suite that only patched the constant would read and write at
   the variable's path instead.

This is not stylistic. `save_habits` writes for real, so a test that skips
either step can write to the developer's own habits. Both suites have a base
that does both: `BehaviourTests.setUp` in `tests/test_storage.py` (via the
`isolate_data_file` helper there, also used by `DataLocationTests`) and
`HandlerTestCase` in `tests/test_cli.py` (which also gives you `run_cli()`,
returning `(exit_code, stdout, stderr)`). Inherit one rather than rolling your
own.

To check the isolation still holds, run the suite with the variable set — it
must pass, and must not create that file:

```bash
HABIT_TRACKER_DATA=/tmp/canary.json python -m unittest discover -s tests
```

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
