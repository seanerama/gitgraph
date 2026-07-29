# Stage 2: Serve dashboard API and minimal shell

- **Type:** feature
- **Depends on:** 1 (needs a populated `commit-store` SQLite file to query)

## Objectives

The second half of the walking skeleton: a real HTTP server reading Stage 1's
SQLite output and answering real queries per the frozen `dashboard-api`
contract, plus a bare-minimum page that proves the browser round-trip works.
This closes the loop end-to-end: repo on disk → `gitgraph analyze` →
`gitgraph serve` → a page in a browser showing real numbers from that repo.

## What to build

- `gitgraph/api.py` — FastAPI app implementing, against `contracts/dashboard-api.md`:
  - `GET /api/summary` — real query over `commits`/`file_changes` (commit
    count, contributor count via distinct author_email, first/last commit
    dates, head_sha/repo_path from `meta`). `total_code_lines` may be `null`
    for now (no `snapshots` data until the later analyzer stage) — that's a
    valid, additive-compatible partial response, not a contract violation.
  - `GET /api/commits` — nodes with parents/refs, filtered by `since`/`until`/
    `branch` query params per contract.
  - **Not built this stage:** `/api/metrics/loc`, `/api/metrics/churn` —
    depend on data (`snapshots`) or aggregation work not yet justified before
    the skeleton itself is proven; next stages layer these on additively.
- `gitgraph/web/index.html` + a small vanilla-JS file — server-rendered
  static shell (per ADR 0001) that fetches `/api/summary` and `/api/commits`
  on load and renders: the summary numbers, and a plain `<ul>` of the most
  recent commits (sha, author, subject) — explicitly NOT the D3 graph yet.
  That's a clearly separate later stage; this stage only proves data flows
  from SQLite to a real browser.
- `gitgraph/cli.py` — add `gitgraph serve [--db PATH] [--port 8000]`, binds
  `127.0.0.1` only (no `0.0.0.0`) per ADR 0002 (local-only, no auth yet).
- `Dockerfile` — builds an image (`ghcr.io/seanerama/gitgraph`) that runs
  `gitgraph serve`; this is what "deploys" means for this stage per ADR 0002
  (container builds and runs locally, no remote target yet).

## Interface contracts

- **Exposes:** `contracts/dashboard-api.md` v1 — this stage implements
  `/api/summary` and `/api/commits` only; the other two endpoints in that
  contract are implemented by later stages (the contract's shape is frozen,
  not the implementation timeline).
- **Consumes:** `contracts/commit-store.md` v1 (read-only, via Stage 1's
  `gitgraph/storage.py` connection helper — do not reopen or reinterpret the
  schema independently).

## Testing requirements

- Integration test: reuse Stage 1's fixture-repo builder, run `gitgraph
  analyze` into a temp DB, then use FastAPI's `TestClient` to hit
  `/api/summary` and `/api/commits` and assert the JSON matches known values
  from the fixture repo (exact commit count, exact head sha, exact parent
  list for the fixture's merge commit).
- A smoke test that `gitgraph serve` actually starts and binds to
  `127.0.0.1` (not `0.0.0.0`) — this is a real security property (ADR 0002:
  local-only, no auth), not just a nice-to-have.
- **UI-smoke asset** (per acceptance conditions below): a short manual/scripted
  check — run `gitgraph serve`, open `http://127.0.0.1:8000/`, confirm the
  page shows a non-zero commit count and a non-empty recent-commits list
  matching the analyzed repo. Author this as a checklist in
  `stage-instructions/` or a simple script the Operator can re-run post-deploy.

## Acceptance conditions

- [ ] Kill-switch / dark-launch flag — **N/A, same justification as Stage 1**:
      `gitgraph serve` is an explicitly-invoked local CLI command, bound to
      localhost only, not a feature flag inside an always-on running service.
- [ ] UI-smoke "observably-works" check authored (see Testing requirements) —
      first real user-facing surface in this project, so this gate applies
      for real here.
- [ ] Additive migration only — no schema changes in this stage (read-only
      consumer of Stage 1's schema).
- [ ] Existing suite stays green; CI all-green — extend `ci.yml` to also
      build the `Dockerfile` and run the container long enough to curl
      `/api/summary` successfully, satisfying ADR 0002's local "deploy" bar.

## Pipeline test: YES

Together with Stage 1, this completes the walking skeleton required by
`stack-and-topology`: compiles, runs, passes a real test, green in CI, and
"deploys" (container builds and runs locally, per ADR 0002). This is the gate
that must go green before any further feature stage is planned.
