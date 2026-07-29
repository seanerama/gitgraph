# Contract: dashboard-api

- **Status:** frozen v1
- **Owner:** `api` module (FastAPI) — served alongside the static `web` shell
  by `gitgraph serve`

## Exposes

A local-only (no auth in v1 — bound to localhost per ADR 0002) JSON HTTP API
that the `web` dashboard's D3/vanilla-JS panels fetch from. All endpoints are
`GET`, read-only, and scoped to the single repo the running `gitgraph serve`
instance was pointed at (multi-repo/hosted mode is out of scope until ADR
0002 is revisited).

## Consumes

Reads from the `commit-store` contract's SQLite file. Does not write to it.

## Schema / wire

Base path: `/api`. All responses `Content-Type: application/json`. All
timestamps ISO 8601. Shared query params on time-series/graph endpoints:

- `since` (ISO 8601 date, optional — defaults to repo's first commit)
- `until` (ISO 8601 date, optional — defaults to now)
- `branch` (ref name, optional — defaults to the repo's default branch)

Every error response uses the envelope `{"error": {"message": string, "code":
string}}` with a non-2xx status.

### `GET /api/summary`

Repo-level totals for the header panel.

```json
{
  "repo_path": "/path/to/repo",
  "head_sha": "abc123...",
  "commit_count": 2481,
  "contributor_count": 19,
  "total_code_lines": 87200,
  "first_commit_at": "2019-03-01T00:00:00Z",
  "last_commit_at": "2026-07-29T18:00:00Z"
}
```

### `GET /api/commits`

Commit-graph nodes and edges for the top DAG panel, filtered by
`since`/`until`/`branch`.

```json
{
  "nodes": [
    {
      "sha": "abc123...",
      "parents": ["def456..."],
      "author_name": "...",
      "author_email": "...",
      "authored_at": "2026-07-29T18:00:00Z",
      "subject": "...",
      "refs": ["main", "v1.2.0"]
    }
  ]
}
```

### `GET /api/metrics/loc`

Lines-of-code-over-time series (from `commit-store.snapshots`) for the LOC
panel. Additional query param `interval` (`day` | `week` | `commit`, default
`week`).

```json
{
  "interval": "week",
  "series": [
    { "date": "2026-07-01", "language": "Python", "code_lines": 41000 },
    { "date": "2026-07-01", "language": "TypeScript", "code_lines": 12000 }
  ]
}
```

### `GET /api/metrics/churn`

Additions/deletions/net/files-changed per interval (derived from
`commit-store.file_changes` joined to `commits`), for the churn panel. Same
`interval` param as `/api/metrics/loc`.

```json
{
  "interval": "week",
  "series": [
    { "date": "2026-07-01", "additions": 3400, "deletions": 1200, "net": 2200, "files_changed": 58 }
  ]
}
```

## Versioning

Frozen at **v1**. Changes are **additive only** — a breaking change is a NEW
contract, not an edit (framework-spec §4.3). Every consumer depends on this
shape. Concretely: new endpoints, new optional query params, and new optional
response fields are fine; removing/renaming a field or changing a field's
type or meaning is not — ship a new contract (e.g. `dashboard-api-v2`)
instead. `/api/contributors` and other panels from the feature catalog are
expected additive endpoints, not yet defined here.
