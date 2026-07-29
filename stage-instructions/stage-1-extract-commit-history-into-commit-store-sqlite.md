# Stage 1: Extract commit history into commit-store SQLite

- **Type:** feature
- **Depends on:** none

## Objectives

The first half of the walking skeleton (ADR 0001/0002): a real, working
extraction pipeline that turns an on-disk Git repository into a populated
SQLite database matching the frozen `commit-store` contract. No API, no UI —
just `git log` in, correct rows out. Everything downstream (Stage 2's API,
later metric panels) reads this data, so it must be right, not just present.

## What to build

- Python package `gitgraph/` with:
  - `gitgraph/extractor.py` — shells out to
    `git log --all --date-order --pretty=format:'%H|%P|%aI|%an|%ae|%cI|%cn|%ce|%s' --numstat`
    (plus a separate pass or `%b` handling for commit body) against a target
    repo path, plus `git show-ref` for branch/tag refs, and writes rows into
    `commits`, `commit_parents`, `refs`, `file_changes` per the `commit-store`
    schema. Handle renames (`R###` numstat lines → `change_type='rename'` +
    `old_path`) and binary files (`-\t-\t<path>` → `is_binary=1`,
    additions/deletions NULL).
  - `gitgraph/storage.py` — creates the SQLite file (if absent) from the
    `commit-store` DDL, exposes a connection/session helper other modules
    reuse (Stage 2's `api` module will import this, not redefine the schema).
  - `gitgraph/cli.py` — `gitgraph analyze <repo-path> [--db PATH]` entry point
    (default `--db` = `.gitgraph/<repo-name>.db`). Writes the `meta` row
    (repo_path, head_sha, extracted_at, gitgraph_version). Re-running
    `analyze` on the same DB fully replaces `commits`/`commit_parents`/
    `refs`/`file_changes` (simplest correct behavior for v1 — no incremental
    diffing yet).
  - `pyproject.toml` packaging the `gitgraph` console script.
- **Explicitly out of scope for this stage:** the `snapshots` table / `scc`
  integration (analyzer module) — that's a later stage layered on top of this
  one once the skeleton is proven end-to-end.

## Interface contracts

- **Exposes:** a populated SQLite file conforming to `contracts/commit-store.md`
  v1 (`meta`, `commits`, `commit_parents`, `refs`, `file_changes` tables —
  `snapshots` left empty, which is valid per that schema).
- **Consumes:** local `git` CLI (must be on PATH; no libgit2/pygit2
  dependency — keeps the stack boring per ADR 0001).

## Testing requirements

- Integration test: build a small fixture Git repo in a temp dir at test
  setup time (a handful of real commits via `subprocess` calls to `git init`/
  `git commit`, including at least one merge and one rename, so both code
  paths are exercised — not a checked-in `.git` fixture, which is fragile
  across Git versions/CI). Run `gitgraph analyze` against it, then assert
  directly against the resulting SQLite file: exact commit count, correct
  parent edges for the merge commit, correct `change_type='rename'` +
  `old_path` for the renamed file, correct ref names.
- Unit tests for the `numstat` line parser (binary line, rename line, normal
  add/delete line) — this is the fiddliest bit of the extractor and easiest
  to get subtly wrong.
- This is the **first pipeline test** — see Pipeline test line below.

## Acceptance conditions

- [ ] Kill-switch / dark-launch flag — **N/A, justified deviation**: this
      stage ships a CLI command (`gitgraph analyze`) invoked explicitly by
      the operator, not a running-service feature with blast radius that
      needs a dark-launch toggle. Nothing executes unless the user runs the
      command.
- [ ] CLI-smoke (stands in for UI-smoke — no UI surface exists yet): running
      `gitgraph analyze <fixture-repo>` against a real small repo produces a
      SQLite file with a non-zero, correct `commits` row count, verifiable by
      `sqlite3 <db> "select count(*) from commits"` — this is the
      "observably works" check for this stage.
- [ ] Additive migration only — this stage originates the `commit-store`
      schema fresh (no prior schema exists to migrate); DDL must match
      `contracts/commit-store.md` v1 exactly, no deviation.
- [ ] Existing suite stays green; CI all-green (extends `.github/workflows/ci.yml`
      with a Python test job — first real test gate beyond the hygiene checks).

## Pipeline test: YES

The fixture-repo → `gitgraph analyze` → assert-SQLite-contents integration
test above is the first real (non-hygiene) CI gate for this project — it
proves the spine, per the walking-skeleton goal in ADR 0001/`stack-and-topology`.
