# Stage 3: Analyze a repo directly from a Git URL

- **Type:** feature
- **Depends on:** none

## Objectives

`gitgraph analyze <target>` currently rejects anything that isn't already an
on-disk git repo (`gitgraph/cli.py` checks `(repo_path / ".git").exists()`).
The user wants to point GitGraph straight at a GitHub URL (or any git URL)
and have it clone and analyze in one step — no manual `git clone` first.
This closes that gap per ADR 0003: full (never shallow) clone-or-update into
a persistent local cache, then hand off to the existing, unmodified
extractor.

## What to build

- `gitgraph/source.py` (new module) — `resolve_target(target: str) -> Path`:
  - Detects whether `target` is a URL (`https://`, `http://`, `git://`
    prefixes, or `git@host:owner/repo.git` SSH syntax) vs. a local path
    (everything else — unchanged behavior).
  - For a local path: return it as-is (today's behavior, verbatim — do not
    change existing local-path tests' outcomes).
  - For a URL: compute a deterministic cache directory under
    `.gitgraph/repos/<slug>/` (slug derived from the URL — e.g. a hash or a
    sanitized owner/repo string; must be filesystem-safe and stable for the
    same URL across runs). If the cache dir doesn't exist, `git clone <url>
    <cache-dir>` (full clone, no `--depth`/`--shallow-since` — ADR 0003 is
    explicit that a shallow clone silently corrupts GitGraph's core metrics).
    If it already exists, `git -C <cache-dir> fetch --all` instead of
    re-cloning. Return the cache dir path.
  - Auth is NOT implemented here — delegate entirely to the operator's
    existing git/SSH config (credential helper, SSH agent). If `git
    clone`/`git fetch` fails (private repo, bad URL, network error), surface
    that subprocess's stderr cleanly rather than swallowing it.
- `gitgraph/cli.py` — change `analyze_parser`'s `repo_path` argument to a
  generic `target` (keep `--db` unchanged); call `source.resolve_target(target)`
  to get a local path, then proceed exactly as today (the `.git`/`HEAD`
  existence check now runs against the *resolved* local path, and still
  applies as a sanity check after clone/fetch, in case of an unexpected
  clone failure that didn't raise).
- `gitgraph/extractor.py` — **no changes**. It must keep receiving only a
  local path; URL resolution happens entirely upstream in the CLI layer, per
  ADR 0003.
- `commit-store` `meta.repo_path`: when the input was a URL, store the
  **original URL string** the user passed (not the local cache path) — pass
  the original `target` string through to `extractor.analyze()`'s existing
  `repo_path` recording, distinct from the local path used for the actual
  `git log` calls. (Check how `analyze()` currently derives the value it
  writes to `meta.repo_path` — likely `str(repo_path.resolve())` — and adjust
  so the *displayed/stored* identity is the URL when one was given, while
  the *filesystem operations* still target the resolved local clone dir.)
- `.gitignore` — add `.gitgraph/repos/` (the clone cache) alongside the
  existing `.gitgraph/` ignore, so it's clear this is a separate, larger
  category of local state (per ADR 0003's consequences section).

## Interface contracts

- **Exposes:** nothing new — output is still exactly a `commit-store` v1
  SQLite file (`contracts/commit-store.md`), byte-identical in schema to
  Stage 1/2's output. The only observable difference is that `meta.repo_path`
  may now hold a URL string instead of a local path, which is within that
  column's existing unconstrained TEXT type (not a contract change).
- **Consumes:** local `git` CLI only (`clone`/`fetch`, in addition to the
  existing `log`/`show-ref`/`rev-parse` from Stage 1) — no new dependency,
  no HTTP client library.

## Testing requirements

- Unit tests for `resolve_target`'s URL-vs-path detection: `https://...`,
  `http://...`, `git://...`, `git@host:owner/repo.git`, and a handful of
  local-path inputs (relative, absolute, `.`) — assert URLs are recognized
  as URLs and everything else falls through to the local-path branch
  unchanged.
- Integration test: build a small local "remote" by `git init --bare` in a
  temp dir, push a couple commits into it from a working clone (this
  simulates a real remote without needing actual network access in CI), then
  call `gitgraph analyze file:///path/to/that/bare/repo` (or clone via the
  bare repo's local path used as if it were a URL target — `file://` is a
  real git URL scheme and exercises the real clone codepath without network
  I/O). Assert: first run clones and produces the expected commit count;
  second run against the same target reuses the cache (`fetch` not `clone` —
  assert e.g. via checking the cache dir's `.git` already existed and wasn't
  recreated, or by adding a new commit to the bare repo between runs and
  confirming the second `analyze` picks it up); `meta.repo_path` in the
  resulting db equals the original `file://...` target string, not the local
  cache path.
- A test that a bad/unreachable URL produces a clean CLI error (exit 1,
  stderr message), not a stack trace.
- Existing Stage 1/2 tests (39 total) must stay green, completely unmodified
  in behavior for local-path `analyze` calls.

## Acceptance conditions

- [ ] Kill-switch / dark-launch flag — **N/A, same justification as Stages
      1–2**: `gitgraph analyze` is an explicitly-invoked local CLI command;
      accepting a URL in addition to a path is an input-handling extension
      of an existing command, not a new always-on service surface.
- [ ] UI-smoke: no new *browser* surface (this stage is CLI-only), but author
      a short manual checklist (e.g.
      `stage-instructions/stage-3-cli-smoke.md`) — run `gitgraph analyze
      <a real public GitHub URL> --db .gitgraph/smoke.db`, confirm it clones,
      confirm the printed commit count is non-zero and sane, run it a second
      time and confirm it's noticeably faster (fetch, not full re-clone), then
      run `gitgraph serve --db .gitgraph/smoke.db` and confirm the dashboard
      shows that remote repo's real data.
- [ ] Additive migration only — no `commit-store` schema changes; confirm
      the DDL in `gitgraph/storage.py` is untouched by this stage's diff.
- [ ] Existing suite stays green; CI all-green — CI's existing `docker` job
      already runs `gitgraph analyze .` (a local path) against this repo
      itself; that must keep working unchanged. No new CI job is strictly
      required for this stage (the new integration test using a local
      `file://` bare repo runs fine inside the existing `test` job — it
      needs no real network access), but if a real-network smoke check
      against an actual public GitHub URL is added, it must be clearly
      separated (e.g. a job that's allowed to be flaky/skipped, not a hard
      CI gate) since CI network reliability is not this project's problem to
      solve.

## Pipeline test: NO
