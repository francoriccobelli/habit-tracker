# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This is a **skeleton**, and that is deliberate. `storage.py`'s four functions
raise `NotImplementedError`, and the `cmd_*` handlers in `cli.py` print what
they *would* do. The argparse wiring is real and complete; nothing below it is.

Each stub carries a numbered TODO describing the intended implementation.
Treat those as the spec — they encode decisions already made (atomic writes via
`os.replace`, case-insensitive habit matching, `version` checked before use).
Read the stub before replacing it.

The README's Roadmap section tracks remaining work and should be updated as
items land.

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

Three conventions follow from that split:

- **Handlers return exit codes.** Each `cmd_*` takes the parsed namespace and
  returns an `int` (0 = success) rather than calling `sys.exit`. Tests call
  them directly and assert on the return value.
- **`build_parser()` is split out from `main()`** so tests can inspect the
  parser and check `--help` without running a command.
- **`data_file()` is indirection on purpose.** Nothing hard-codes `DATA_FILE`;
  the accessor is the future home of a `HABIT_TRACKER_DATA` env var and a
  `--data-file` flag, and it is how tests will point at a tmp directory.

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

## Tests

`BehaviourTests` in `tests/test_storage.py` is a skipped class that spells out
what each stub owes: load-returns-empty-when-missing, save/load round-trip,
case-insensitive find. **Unskip these as the implementations land** — they are
the acceptance criteria, not dead code.

Current tests assert shape and wiring rather than behaviour, since there is no
behaviour yet.
