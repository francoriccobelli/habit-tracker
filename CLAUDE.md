# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

All seven commands (`add`, `list`, `done`, `undone`, `remove`, `stats`,
`history`) work end
to end and are tested, and the data file can be redirected with `--data-file`
or `HABIT_TRACKER_DATA`. Every roadmap item in the README is now closed. New
work should add an item there and tick it as it lands.

CI lives in `.github/workflows/ci.yml` (Python 3.10–3.14 on Ubuntu, plus a
Windows job). It runs the suite twice — once with nothing installed, to keep
the stdlib-only promise honest — and re-runs it with `HABIT_TRACKER_DATA` set,
failing if the suite writes to that path. It also smoke-tests the installed
console script, which no unit test reaches. `main` has been pushed, so check
the Actions tab rather than assuming green.

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

Three modules, layered one way with no cycles:

```
storage.py   owns the data file      (never prints)
    ^
render.py    data -> list[str]       (never prints, never opens a file)
    ^
cli.py       argparse and dispatch   (prints; opens nothing)
```

- **`storage.py` never prints.** It is the sole owner of the data file — its
  path, its format, and its migrations. It imports neither of the others.
- **`render.py` never prints and never opens a file.** Every view is a pure
  function returning `list[str]`, which is what lets the calendar be tested as
  a function instead of through captured stdout. It may import `storage` to
  reuse the pure helpers rather than restating that logic.
- **`cli.py` never opens a file.** Argparse, dispatch, and printing what
  `render` hands back.

This is what makes each module testable without the others, and it is the one
rule to preserve when adding features. A new command that needs data asks
`storage` for it; a new view goes in `render`; neither reaches for `pathlib`.

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
  logic. Put the next such helper there too. Formatting is `render.py`'s
  (`plural`, `error`, the three `*_lines` views); the one thing that stays in
  `cli.py` is `_iso_day`, which parses `--date` — argv is the CLI's own input,
  and neither other module reads it. `_iso_day` raises `ValueError` with a
  user-facing message rather than printing, letting `main()`'s existing
  handler render it.
- **`build_parser()` is split out from `main()`** so tests can inspect the
  parser and check `--help` without running a command.
- **`data_file()` is indirection on purpose.** Nothing hard-codes `DATA_FILE`.
  The accessor resolves the path on every call, highest precedence first:
  `--data-file` (stored by `set_data_file()`, which `main()` calls on every run
  so an override cannot outlive it), then `HABIT_TRACKER_DATA`, then
  `DATA_FILE`. Resolution at *call* time is what lets tests redirect the
  constant. `using_override()` reports whether the path came from either
  override — `cmd_list` uses it to decide whether naming the file is useful.
- **Colour is module state in `render.py`, resolved once per run.** `main()`
  calls `render.set_colour(args.color, sys.stdout)` unconditionally, for the
  same reason it calls `set_data_file` — so nothing leaks between the many
  `main()` calls a test process makes. `auto` needs a TTY and an unset
  `NO_COLOR`; `always` overrides both, since an explicit flag beats an ambient
  preference. Every painted string goes through `_paint`, which is the
  identity function when colour is off, so disabled output is byte-for-byte
  what it was before colour existed. **Pad before painting** — escape codes
  lengthen a string without widening it, so padding a painted cell silently
  breaks column alignment.

## Code style

There is no formatter and no linter configured, on purpose — the same reason
there are no runtime dependencies. That makes these conventions hand-held, so
match the file you are in rather than assuming a tool will fix it after.

- **Annotate every signature**, including `-> None` and including test
  methods. Every module under `habit_tracker/` that annotates opens with
  `from __future__ import annotations`; `__init__.py` does not, because it
  annotates nothing.
- **Docstring every module, class, and function** — private helpers included.
  Google style: `Args:` / `Returns:` / `Raises:` when there is something to
  say, one line when there is not. Document the *reasoning*, not the
  signature: `current_streak` spends its docstring on why a streak survives a
  not-yet-done today, which is the part a reader cannot infer.
- **Cross-reference with reST roles** — `:func:`, `:mod:`, `:class:`,
  `:data:` — and ``double backticks`` for literals. This is what the existing
  docstrings use; do not mix in Markdown backticks beside them.
- **Module constants get `#:` comments** above them, as `DATA_FILE` and
  `SCHEMA_VERSION` do.
- **Comments explain why, never what.** Every comment in the codebase earns
  its place by recording a decision or a hazard — why the temp file shares a
  directory with its target, why an empty env value counts as unset. A
  comment restating the line below it is noise.
- **Wrap at 79 columns, 88 is the hard ceiling.** Package code holds to this
  almost everywhere; tests run a little wider where a long assertion reads
  better unbroken.
- **Python source is pure ASCII.** Use `--` in docstrings and comments where
  prose would take an em dash. Markdown files (this one, the README) use real
  em dashes — the restriction is for `.py` files only, and it is currently
  exact: not one non-ASCII byte in the package or the suite.
- **Private helpers take a leading underscore** (`_iso_day`, `_window`,
  `_paint`), and stay out of `__all__`.

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

Beyond that one rule, four conventions the suite already holds to:

- **Write `unittest`, never `pytest`-only features.** The suite is stdlib
  `unittest` so it runs with nothing installed — CI's first job proves that by
  running it in a bare environment. `pytest` is a convenience runner over the
  same tests, not a dependency they may reach for. There is not one `import
  pytest` in `tests/`, and adding one would break that job.
- **Inject time, never freeze the clock.** `current_streak`, `tracked_days`
  and `tracked_since` all take `today: date | None = None` precisely so a test
  can pass a fixed date instead of patching `date.today`. A new helper that
  cares what day it is takes the same parameter.
- **Mock the boundary, nothing else.** `mock` appears only to redirect
  `storage.DATA_FILE`, to sandbox `os.environ`, and to force the Windows
  VT-mode probe in `test_render.py`. There are no network calls and no
  external services to stub, and the pure helpers need no test doubles at all
  — if a new test wants one, that is usually a sign the logic belongs in
  `storage.py` as a pure function instead.
- **Assert on what landed on disk**, not only on printed output — see
  *Writing a new command* below.

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

## Commits

The log is part of the documentation here — several decisions in this project
live in a commit body and nowhere else. Match it.

- **Subject: imperative mood, capitalised, no full stop, 50 characters or
  fewer.** "Add a stats command and fix message pluralization", not "Added" or
  "Adds". Every subject in the log so far is between 25 and 51 characters.
- **Wrap the body at 72 columns**, blank line after the subject.
- **The body explains why, and what was rejected.** This is the part that
  matters. A commit that adds a feature says what the alternative was and why
  it lost — the stats commit explains why the rate window spans backdated
  completions rather than running from `created`, because a reader would
  otherwise assume the simpler thing was an oversight.
- **Name the test that pins a behaviour** when one does, as
  `test_done_rejects_an_unparseable_date` is named in the `undone` commit. It
  tells the next reader where the guarantee is enforced.
- **Say what is unproven.** The CI commit states outright that the workflow
  had not run yet and that the 3.14 job was unverified against the runners.
  Do not let a commit body imply more confidence than the work earned.
- **One logical change per commit**, with the caveat the log already shows: a
  version bump or a docs update may ride along with the change that motivated
  it ("Add an undone command and CI, and bump to 0.2.0"). Unrelated changes
  still get their own commit.
- **End with the `Co-Authored-By:` trailer** when Claude wrote part of it.

Never commit anything from `~/.habit_tracker/` — user data lives outside the
repo specifically so it cannot land in a commit.
