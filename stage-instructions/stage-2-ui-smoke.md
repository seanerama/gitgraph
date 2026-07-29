# Stage 2 UI-smoke checklist

First real user-facing surface in this project (per the stage-2 acceptance
conditions). This is the manual counterpart to the automated checks in
`tests/test_api.py` (`test_index_page_served`,
`test_serve_actually_starts_and_answers_on_127_0_0_1`) — run this after any
deploy to confirm the actual browser round-trip works, not just the API in
isolation.

## Steps

1. Analyze a real repo (any repo with a few commits works — this repo
   itself is fine):

   ```sh
   gitgraph analyze /path/to/some/repo --db .gitgraph/smoke.db
   ```

   Confirm it prints `gitgraph: wrote N commits from ... to .gitgraph/smoke.db`
   with `N > 0`.

2. Start the server:

   ```sh
   gitgraph serve --db .gitgraph/smoke.db --port 8000
   ```

   Confirm the startup line reads `gitgraph: serving .gitgraph/smoke.db on
   http://127.0.0.1:8000/` — **not** `0.0.0.0` (ADR 0002: local-only, no
   auth — this is a real security property, not just style).

3. Open `http://127.0.0.1:8000/` in a browser.

4. Confirm on the page:
   - [ ] The repo path shown matches the repo you analyzed.
   - [ ] The "Commits" stat is a non-zero number matching what step 1
         printed.
   - [ ] The "Contributors" stat is a non-zero number.
   - [ ] "First commit" / "Last commit" dates are populated and look sane
         for the analyzed repo's history.
   - [ ] The "Recent commits" list is non-empty, and the first few entries'
         short SHAs, subjects, and author names match `git log` output for
         that repo (e.g. `git log --oneline -5`).
   - [ ] No error text appears in the red error area at the bottom of the
         page.

5. Confirm the API responds directly too (belt and suspenders):

   ```sh
   curl -s http://127.0.0.1:8000/api/summary | python3 -m json.tool
   curl -s http://127.0.0.1:8000/api/commits | python3 -m json.tool | head -30
   ```

   Both should return `200` with the shapes in `contracts/dashboard-api.md`.

6. Stop the server (`Ctrl-C`) once done.

## Known simplifications (not bugs)

- `total_code_lines` in `/api/summary` is always `null` — the `snapshots`
  table isn't populated until a later analyzer stage. This is a documented,
  additive-compatible partial response, not a contract violation.
- `/api/commits?branch=<name>` interprets "commits on a branch" as the
  ancestor closure of that branch's current tip (walked over
  `commit_parents`), since the `commit-store` schema only stores a
  ref → sha snapshot, not full historical branch membership.
- The commit graph itself (D3, zoom/pan, synced panels) is out of scope for
  this stage — the recent-commits list is a plain `<ul>` on purpose.
