# 0003. Support analyzing a remote repo by URL

- **Status:** Accepted
- **Date:** 2026-07-29

## Context

`gitgraph analyze` currently requires a local filesystem path — verified in
`gitgraph/cli.py`: it checks `(repo_path / ".git").exists()` and rejects
anything else. The user wants to point GitGraph directly at a GitHub URL
(e.g. `https://github.com/owner/repo`) and have it build the graph without a
manual `git clone` step first.

This is a CLI convenience decision, not a hosted-service decision — the tool
is still explicitly invoked by an operator on their own machine (ADR 0002:
local-only, no remote deploy target, no auth). The operator could already
run `git clone <url> && gitgraph analyze <path>` themselves; this ADR is
about GitGraph doing that clone step internally, not about opening the tool
up to untrusted/multi-tenant input. The harder question ADR 0002 flagged —
"whose repos does a *hosted* GitGraph analyze" — remains deferred and
untouched by this decision.

Two forces shape the design:
- `idea.md` explicitly lists "shallow clones missing old history" as a known
  failure mode — GitGraph's entire value proposition (accurate commit
  history, LOC-over-time, contributor metrics) depends on having the full
  history, so however the clone happens, it must not be shallow.
- Re-cloning a large repo from scratch on every `analyze` run is wasteful
  and slow. Analysis is expected to be re-run periodically (idea.md's
  "repository health timeline" framing implies revisiting a repo over time).

## Decision

- `gitgraph analyze <target>` accepts either a local filesystem path (today's
  behavior, unchanged) or a Git URL (`https://`, `http://`, `git://`, or
  `git@host:owner/repo.git` SSH syntax). Detection is by a simple prefix/
  pattern check on `<target>`, not a network probe.
- When `<target>` is a URL, GitGraph clones it **in full** (no `--depth`) via
  a plain `git clone <url> <cache-dir>` subprocess — same "boring, git-CLI-
  subprocess" approach as the existing extractor (ADR 0001), no new library
  dependency.
- Clones land in a deterministic local cache directory keyed by a hash/slug
  of the URL (e.g. `.gitgraph/repos/<slug>/`), not a throwaway temp dir. If
  a cache entry already exists for that URL, GitGraph runs `git fetch --all`
  against it and reuses the existing clone rather than re-cloning from
  scratch — much cheaper for repeat analysis of the same repo, and the
  existing extractor already reads the full ref set via `--all`, so a fetch
  is sufficient to pick up new history.
- Authentication is delegated entirely to the operator's existing git/SSH
  configuration (credential helper, SSH agent, etc.) — GitGraph does not
  implement or store any credentials itself. This covers private repos the
  operator already has access to, for free, with zero new code.
- The `commit-store` contract's `meta.repo_path` column (TEXT, no format
  constraint) stores the **original target string the user passed** (the URL
  itself, not the local cache path) when analyzing a URL — so a database
  produced from a URL-based analysis is self-describing about its source.
  This is a value-only decision within the existing frozen column, not a
  schema change.

## Alternatives considered

- **Shallow clone (`--depth 1` or `--shallow-since`)** — much faster for a
  first look at a huge repo, but silently produces wrong data for GitGraph's
  core metrics (missing merge commits, wrong first-commit dates, undercounted
  contributors) with no indication to the user that anything is missing.
  Rejected outright — `idea.md` names this exact failure mode as a known
  trap. If repo-size performance becomes a real problem, the right fix is a
  progress indicator or a documented "this may take a while for large repos"
  warning, not silently wrong data.
- **Fresh temp-dir clone every run, discarded after** — simpler (no cache
  invalidation to think about) but wasteful: full clones of large repos are
  slow, and re-running `analyze` periodically is the expected usage pattern
  per `idea.md`'s "health timeline" framing. Rejected in favor of the
  persistent, fetch-updated cache.
- **A Python git library (GitPython, pygit2/libgit2, dulwich)** instead of
  shelling out to `git clone`/`git fetch` — would avoid one more subprocess
  call, but ADR 0001 already committed to boring git-CLI subprocesses for
  the exact same reasons (no new binding/build dependency, matches the
  existing extractor's approach); shelling out again keeps that consistent
  rather than introducing a second way of talking to git in the same
  codebase.
- **Building our own credential/token handling for private repos** — rejected
  as unnecessary scope; the operator's local git config already solves this
  for a locally-invoked CLI tool, and building bespoke auth would only matter
  for the hosted/multi-tenant case ADR 0002 explicitly deferred.

## Consequences

- `gitgraph analyze` gains a second input mode with no change to the
  extractor itself — `extractor.analyze()` still only ever sees a local
  path; the URL-vs-path branching and the clone/fetch step live entirely in
  the CLI layer ahead of it.
- `.gitgraph/repos/` becomes a second, larger category of local state beyond
  the per-repo `.db` files — needs its own `.gitignore` entry and should be
  mentioned in the UI-smoke/README docs so operators understand what's
  accumulating on disk.
- Because auth is delegated to the operator's git config, failure modes for
  private repos without access surface as a plain `git clone`/`git fetch`
  subprocess error — GitGraph should pass that stderr through cleanly rather
  than swallowing it, so the operator can diagnose it themselves.
- If GitGraph is ever revisited for a hosted/multi-tenant deployment (ADR
  0002's still-open question), this ADR's trust model does **not** carry
  over — cloning arbitrary user-submitted URLs on a shared host is a
  different security posture entirely and must be re-examined from scratch
  at that time, not assumed safe by extension of this decision.
