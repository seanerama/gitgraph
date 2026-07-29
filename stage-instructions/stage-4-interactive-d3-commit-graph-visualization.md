# Stage 4: Interactive D3 commit-graph visualization

- **Type:** feature
- **Depends on:** none

## Objectives

Stage 2's web shell (`gitgraph/web/app.js`) renders recent commits as a
plain `<ul>` — explicitly a placeholder, per its own comment: "This is
explicitly NOT the D3 commit graph — that's a separate later stage." This
stage is that later stage: replace the plain commit list with an actual
interactive, zoomable/pannable DAG rendering of the commit history, per
`idea.md`'s original vision (branch lanes, merge edges, hover detail).

Scope check: this is the graph panel only. The full "synchronized panels"
vision (LOC-over-time, churn, contributors sharing a time-range selector
with the graph) stays deferred — those need endpoints
(`/api/metrics/loc`, `/api/metrics/churn`) that don't exist yet (no
`snapshots` data — see `feature-assessments/walking-skeleton-assessment.md`).
This stage only needs the already-implemented `/api/commits` endpoint.

## What to build

- **Vendor D3 locally, do not use a CDN `<script>` tag.** GitGraph is a
  local-first tool (ADR 0002); a runtime dependency on an external CDN for
  the dashboard to render at all is inconsistent with that. Download a
  single D3 v7 minified build, commit it at `gitgraph/web/vendor/d3.v7.min.js`,
  and reference it with a plain local `<script src="/vendor/d3.v7.min.js">`
  tag in `index.html` — still zero build step, just a vendored file instead
  of a fetched one. Add the new path to `pyproject.toml`'s
  `[tool.setuptools.package-data]` glob (currently `web/*.html`, `web/*.js` —
  needs to also pick up `web/vendor/*.js`).
- `gitgraph/web/graph.js` (new file, or extend `app.js` — executor's call,
  keep it readable) — renders `/api/commits`'s `nodes` (sha, parents, refs,
  author_name, author_email, authored_at, subject) as an SVG DAG using D3:
  - X-axis: commit time (`authored_at`), oldest to newest, left to right.
  - Y-axis / lanes: a simple lane-assignment heuristic (does not need to be
    optimal/crossing-minimal — e.g. assign each ref's lineage a lane and
    reuse a parent's lane for its first-listed child, allocating a new lane
    when a branch forks) so parallel branches are visually distinguishable,
    roughly matching `idea.md`'s sketch:
      ```
      main ─●─●──────●──────●────────●──────●
               ╲    ╱        ╲       ╱
      feature   ●──●          ●─●───●
      ```
  - Edges: a line/curve from each commit to each of its parents (a merge
    commit has 2+ edges, drawn distinctly from normal parent edges — e.g. via
    styling, not necessarily a different shape).
  - **Zoom + pan** (D3's `d3.zoom()` on the SVG) — this is a hard functional
    requirement, not optional polish; it's the reason a real graph library is
    justified here.
  - **Hover tooltip** showing, per `idea.md`'s exact spec: commit message
    (subject), author, date, branch/ref(s), parent commit(s) (short shas),
    files-changed count is NOT available from `/api/commits` in v1 — omit it
    rather than adding a new endpoint call this stage doesn't need; note the
    omission in code/UI-smoke doc, don't silently drop it without saying so.
  - **Scale guard:** `/api/commits` has no pagination in the frozen contract
    and can return the full history. Cap client-side rendering at a sane
    default (e.g. the most recent 300 commits by `authored_at`) and show a
    visible note when truncated ("showing 300 of N commits") rather than
    silently rendering a subset or trying to render everything and hanging
    the browser on a large repo. Full-history rendering performance is
    explicitly a follow-on concern, not solved here.
- `gitgraph/web/index.html` — replace the `<ul id="commits">` section with
  an `<svg>` (or container div D3 attaches to) for the graph; keep the
  existing summary stat panel unchanged.
- `gitgraph/api.py` — **no changes**. This stage is frontend-only.

## Interface contracts

- **Exposes:** nothing new — pure frontend consumer.
- **Consumes:** `contracts/dashboard-api.md` v1's existing `GET /api/commits`
  only. No new query params, no contract change.

## Testing requirements

- No backend logic changes, so no new Python integration tests are required
  for correctness of data — Stage 2's existing `/api/commits` tests already
  cover that the data is right.
- Add a lightweight test that the new static assets are served correctly:
  `GET /vendor/d3.v7.min.js` returns 200 with a JS content-type, and
  `index.html` no longer contains `<ul id="commits">` (i.e. actually swapped
  out, not left dead in the DOM alongside the new graph).
- **UI-smoke asset** (this is the primary verification for this stage, since
  the interesting behavior is visual/interactive and can't be meaningfully
  unit-tested): author `stage-instructions/stage-4-ui-smoke.md` — run
  `gitgraph serve` against an already-analyzed repo with some branching
  history (the fixture-repo pattern from Stage 1's tests, or a real repo),
  open the dashboard, and confirm:
  - [ ] The graph renders visible nodes and edges (not blank/broken).
  - [ ] Merge commits show multiple incoming edges.
  - [ ] Scroll-to-zoom and drag-to-pan both work.
  - [ ] Hovering a node shows a tooltip with subject, author, date, refs,
        and parent shas.
  - [ ] If the analyzed repo has >300 commits, a "showing N of M" note is
        visible; if ≤300, no truncation note appears.
  - [ ] No console errors in the browser dev tools.

## Acceptance conditions

- [ ] Kill-switch / dark-launch flag — **N/A, same justification as Stages
      1–2**: this replaces a placeholder view in an explicitly-invoked local
      CLI tool's own UI; there's no running-service blast radius to gate.
- [ ] UI-smoke "observably-works" check authored (see above) — this stage's
      value is entirely in the interactive visual surface, so this gate
      applies in full.
- [ ] Additive migration only — N/A, no schema or API changes at all this
      stage (pure frontend).
- [ ] Existing suite stays green; CI all-green — no new CI job needed beyond
      running the existing `test` suite (extended with the two lightweight
      static-asset checks above) and the existing `docker` job's curl of
      `/api/summary` (unaffected by this stage).

## Pipeline test: NO
