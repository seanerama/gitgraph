# Stage 4 UI-smoke checklist

The interesting behavior in this stage (an interactive, zoomable/pannable D3
commit-graph DAG) is visual/interactive and can't be meaningfully
unit-tested. This is the primary verification for this stage — the
automated counterpart in `tests/test_api.py`
(`test_vendored_d3_is_served`, `test_graph_js_is_served`,
`test_index_page_no_longer_has_placeholder_commit_list`) only proves the
static assets are served and the old placeholder markup is gone; it does
not exercise the actual rendering, lane assignment, zoom/pan, or tooltip.

## Steps

1. Build a repo with some real branching history to analyze. Either:
   - use any real repo with merge commits (this repo itself, once it has a
     merge, works), or
   - build the fixture-repo pattern from `tests/test_integration.py`'s
     `build_fixture_repo()` (a root commit, a rename, a `feature` branch,
     and a `--no-ff` merge back into `main`) — e.g. via a scratch script
     that imports and calls it, or by hand with `git init` / `git checkout
     -b feature` / `git merge --no-ff feature`.

2. Analyze it and start the server:

   ```sh
   gitgraph analyze /path/to/some/repo --db .gitgraph/smoke.db
   gitgraph serve --db .gitgraph/smoke.db --port 8000
   ```

   Confirm the startup line reads `http://127.0.0.1:8000/`, not `0.0.0.0`
   (ADR 0002, same as Stage 2).

3. Open `http://127.0.0.1:8000/` in a browser and open the dev tools
   console before interacting, so you catch any errors during load.

4. Confirm on the page:
   - [ ] The graph renders visible nodes (circles) and edges (lines/curves)
         under the "Commit graph" heading — not blank, not broken.
   - [ ] Nodes are laid out left-to-right in chronological order
         (`authored_at` oldest to newest).
   - [ ] A merge commit (if the analyzed repo has one) shows **two or more
         incoming edges** converging on it, and the non-primary-parent
         edge(s) are visually distinct (dashed/orange in this
         implementation) from a normal single-parent edge.
   - [ ] Scroll-to-zoom over the graph zooms in/out.
   - [ ] Click-and-drag over the graph pans it.
   - [ ] Hovering a node shows a tooltip containing: the commit subject,
         author name, date, ref(s) (or "(none)" if the commit has no refs
         pointing at it), and parent short-SHA(s) (or "(root commit)" for
         a root).
   - [ ] If the analyzed repo has **more than 300 commits**, a note reading
         `showing 300 of N commits` appears above the graph. If the repo
         has 300 or fewer commits, no truncation note appears (the `<p
         id="graph-note">` element stays `hidden`).
   - [ ] No errors appear in the browser dev tools console.
   - [ ] The summary stat panel above the graph (repo path, commit count,
         contributors, first/last commit date) still renders correctly —
         confirms `app.js`'s unrelated `renderSummary()` logic wasn't
         broken by this stage's changes.

5. Stop the server (`Ctrl-C`) once done.

## Known simplifications / deliberate omissions (not bugs)

- **Lane assignment is a simple heuristic, not crossing-minimal.** It walks
  commits in chronological order, reuses a parent's lane for its
  first-listed chronological child, and allocates a new lane on a fork or
  when a merge commit needs to reconcile a second parent. On repos with
  complex branch topology this can look busier than a hand-tuned graph
  layout (e.g. `gitk`) — that's expected, not a defect, per the stage spec.
- **Files-changed count is intentionally omitted from the hover tooltip.**
  `idea.md`'s original tooltip wishlist included it, but `/api/commits` in
  the frozen v1 `dashboard-api` contract doesn't return numstat data, and
  adding it would require a new endpoint / contract change — explicitly out
  of scope for this stage. Noted in code (`gitgraph/web/graph.js` header
  comment) as well as here.
- **Scale guard caps rendering at the most recent 300 commits** by
  `authored_at` — full-history rendering performance for very large repos
  is an explicit follow-on concern, not solved in this stage.
- **D3 is vendored locally** (`gitgraph/web/vendor/d3.v7.min.js`), not
  loaded from a CDN — consistent with ADR 0002 (local-first tool). No
  network access is required to load the dashboard.
- The synchronized-panels vision from `idea.md` (LOC-over-time, churn,
  contributors sharing a time-range selector with the graph) stays
  deferred — those need `/api/metrics/loc` and `/api/metrics/churn`, which
  don't exist yet (see `feature-assessments/walking-skeleton-assessment.md`).
  This stage is the graph panel only.
