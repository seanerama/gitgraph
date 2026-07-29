# 0001. Choose stack and topology for GitGraph

- **Status:** Accepted
- **Date:** 2026-07-29

## Context

GitGraph turns a Git repository's history into an interactive "health timeline":
a commit-graph panel synced against LOC-over-time, churn, and contributor panels,
with a shared time-range selector. The source idea (`idea.md`) sketches Python +
Git-CLI extraction, `scc`/`tokei`/`cloc` for snapshot LOC, SQLite/DuckDB for
storage, and Plotly/D3 for the front end, with FastAPI "only if the dashboard
needs a backend" — it does, since panels need to query pre-aggregated series and
the commit DAG on demand rather than shipping the whole history to the client.

The `stack-and-topology` guide recommends boring, well-supported stacks, a
modular monolith by default, and server-rendered + progressive enhancement over
a SPA unless the UX genuinely needs a rich client.

## Decision

- **Language/runtime:** Python 3 for the extractor, snapshot analyzer, and API
  server. Git plumbing via `git` CLI subprocesses (matches the exact commands
  already prototyped in `idea.md`); snapshot LOC via `scc` (fast, single static
  binary, good language coverage) shelled out per sampled commit.
- **Storage:** SQLite (stdlib `sqlite3`, single portable file, zero ops). Holds
  commits, parent edges, per-file numstat, periodic LOC snapshots, and
  contributors.
- **API/serving:** FastAPI, one process, serving both a small JSON API
  (commit-graph nodes/edges, metric time series, summary) and the static
  dashboard shell.
- **Frontend:** No SPA framework. A single server-rendered HTML shell +
  vanilla JS/D3.js for the commit DAG and synced metric panels, fetching from
  the JSON API. No build step.
- **Topology:** Modular monolith, one service, one container image
  (`ghcr.io/seanerama/gitgraph`). Internal modules: `extractor` (walks git log,
  writes commits/edges/numstat), `analyzer` (periodic `scc` snapshots),
  `storage` (SQLite schema + queries), `api` (FastAPI routes), `web` (static
  shell + D3 panels). CLI entry points: `gitgraph analyze <repo-path>` and
  `gitgraph serve`.

## Alternatives considered

- **DuckDB instead of SQLite** — better analytical (columnar) query
  performance for large aggregations, but adds a dependency and an ops
  surface the project doesn't need yet at single-repo scale. Revisit if
  metric-query latency becomes a real problem; the `storage` module is the
  seam that would absorb the swap.
- **React/Vue SPA frontend** — the guide's default lean is server-rendered +
  progressive enhancement, and normally that's the call here too. Deviation:
  the core value of this product *is* an interactive, brushable, multi-panel
  visualization (synced zoom/pan across a commit DAG and several time series)
  — that's irreducibly client-rendered SVG/canvas work, not content a server
  can meaningfully pre-render. Choosing D3 + vanilla JS over a framework keeps
  the "no SPA" spirit (no build pipeline, no client router, no component
  framework) while accepting that the panels themselves are rich-client by
  necessity.
- **Node/TypeScript full stack** (`simple-git` + `better-sqlite3` + D3) —
  viable and arguably unifies the language with the frontend, but `idea.md`'s
  own prototyping and the broader Git-analytics tooling ecosystem (PyDriller,
  `scc`/`tokei`/`cloc` as separate binaries either way) lean Python; kept it
  boring by following the already-validated shape.
- **Multi-service split (extractor service + API service)** — no real reason
  yet: no independent scaling need, no team/ownership boundary, single
  runtime. Stayed a modular monolith per the guide's default.

## Consequences

- One image, one CI matrix entry, one deploy artifact — cheapest possible
  ops surface for a v1.
- `scc` becomes an external tool dependency (not a Python package) — CI and
  the container image must install it explicitly.
- Because there's no build pipeline for the frontend, adding any JS dependency
  beyond D3 later (e.g. a table/grid library) means introducing a bundler at
  that point — accepted as a deliberate later cost in exchange for a simple v1.
- The `storage` module's SQLite schema is the seam most likely to need a
  breaking change if repo scale outgrows single-file SQLite; that's the
  documented escape hatch to DuckDB.
