# Assessment: analyze-by-URL + interactive commit-graph visualization

- **Date:** 2026-07-29
- **Request:** User ask — "I want to be able to just point the app at a
  github url and have it build the graph. we also need to display visual
  graphs via interactive html."
- **Decision:** ACCEPT as 2 independent stages (3, 4), no dependency between
  them. Both are additive on top of the merged walking skeleton (Stages 1–2).
- **Refs:** ADR 0003 (new, this batch); `contracts/commit-store.md`,
  `contracts/dashboard-api.md` (both unmodified by this batch);
  `feature-assessments/walking-skeleton-assessment.md` (prior deferral of
  exactly this D3 work).

## Verification against the live codebase

| Claim (from the request) | Reality (verified 2026-07-29, gitgraph @ `6b862ca`) | Consequence |
|---|---|---|
| "just point the app at a github url" implies this doesn't work today | Confirmed — `gitgraph/cli.py`'s `analyze` command does `(repo_path / ".git").exists()` on `Path(args.repo_path).resolve()`; a URL string resolved as a path fails this check and the command exits 1 | Stage 3 needed |
| "display visual graphs via interactive html" implies none exists today | Confirmed — `gitgraph/web/app.js`'s `renderCommits()` builds a plain `<ul>` of `<li>` text rows; the file's own comment states "This is explicitly NOT the D3 commit graph — that's a separate later stage" | Stage 4 needed, and was already anticipated/named in Stage 2's own code comments and in the walking-skeleton assessment's "deliberately deferred" list |
| The backend has the data a graph needs | Confirmed — `contracts/dashboard-api.md`'s `GET /api/commits` already returns `sha`, `parents`, `refs`, `author_name`, `author_email`, `authored_at`, `subject` per node; this is sufficient for a DAG render with hover detail, no new endpoint required | Stage 4 is frontend-only, zero backend changes |
| Cloning a URL could threaten the "local-only, no remote deploy" posture (ADR 0002) | Checked ADR 0002's own text — it deferred a *hosted, multi-tenant* deployment question ("whose repos does a hosted GitGraph analyze"), which is a different concern from a locally-invoked CLI cloning a URL the operator chose. Confirmed no conflict; documented the distinction explicitly in the new ADR 0003 so this doesn't get conflated later | No amendment to ADR 0002 needed; new ADR 0003 instead |

## Contract safety

Neither `commit-store` nor `dashboard-api` (both frozen v1) are touched by
either stage:

- Stage 3 changes `meta.repo_path`'s *value* (a URL string instead of a local
  path when analyzing a URL) but not the column's type or constraints — that
  column was always unconstrained TEXT. Not a contract change.
- Stage 4 is a pure consumer of the existing `GET /api/commits` shape — adds
  no query params, changes no response fields.

## Stage map

3. **Analyze a repo directly from a Git URL** (feature, no deps) —
   `gitgraph analyze <url-or-path>` detects a URL, full-clones (never
   shallow — `idea.md`'s own documented failure mode) or `fetch`-updates an
   existing cache under `.gitgraph/repos/`, then hands off to the unmodified
   Stage 1 extractor. Auth delegated to the operator's own git/SSH config —
   no credential handling built. See ADR 0003 for the full reasoning
   (shallow-vs-full clone, cache-vs-throwaway-clone, why not a Python git
   library).
4. **Interactive D3 commit-graph visualization** (feature, no deps) —
   replaces Stage 2's placeholder `<ul>` with a real zoomable/pannable SVG
   DAG (D3, vendored locally rather than CDN-loaded, consistent with
   GitGraph being a local-first tool), branch-lane layout, merge edges,
   hover tooltips per `idea.md`'s original spec. Client-side rendering is
   capped at the most recent 300 commits by default with a visible
   truncation note — full-history rendering performance is named as a
   follow-on concern, not solved here.

Stages 3 and 4 are independent and parallelizable — Stage 4 already has data
to render today from any locally-analyzed repo; it doesn't need Stage 3 to
land first. Together they satisfy the user's request: `gitgraph analyze
<github-url>` then `gitgraph serve` shows that remote repo's real history as
an interactive graph.

## Deliberately deferred

- The full synced-multi-panel vision from `idea.md` (LOC-over-time, churn,
  contributors sharing a time-range selector with the graph) — still blocked
  on the `snapshots`/`scc` analyzer work and the `/api/metrics/loc` and
  `/api/metrics/churn` endpoints, all already named as deferred in the
  walking-skeleton assessment and unaffected by this batch.
- Optimal/crossing-minimized graph-layout algorithms (matching what
  tools like `gitk` or GitKraken do) — Stage 4 asks for a "good enough"
  lane heuristic, not a polished layout algorithm; revisit only if the
  simple heuristic proves visually confusing on real repos.
- Rendering performance for very large histories (thousands of commits) —
  Stage 4's 300-commit cap is an explicit, visible stopgap, not a real
  solution; a proper fix (virtualized rendering, server-side pagination via
  `since`/`until`, or a dedicated "load more" affordance) is future work if
  it turns out to matter in practice.
- Credential/token management for private repos in a hosted context — Stage
  3 explicitly punts this to the operator's local git config; only relevant
  again if/when ADR 0002's hosted-deployment question is revisited.

## Outcome

Pending — Stages 3 and 4 handed to `/verity:build`.
