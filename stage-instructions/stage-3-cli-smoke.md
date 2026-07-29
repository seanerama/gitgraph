# Stage 3 CLI-smoke checklist

No new browser surface in this stage (per the stage-3 acceptance
conditions) — the new behavior is entirely in `gitgraph analyze`'s input
handling. This is the manual counterpart to the automated `file://`
bare-repo tests in `tests/test_analyze_url.py`, which exercise the same
clone/fetch codepath with zero real network access. Run this checklist
against a real public GitHub URL to confirm the real-network path (git
auth, real clone timings, dashboard round-trip) actually works end to end.

## Steps

1. Pick any small-to-medium real public GitHub repo you don't mind cloning
   locally (e.g. `https://github.com/octocat/Hello-World` or a repo of your
   own). Make sure `.gitgraph/smoke.db` and `.gitgraph/repos/` don't already
   exist from a previous run, or just use a fresh working directory.

2. Run the first analyze:

   ```sh
   gitgraph analyze https://github.com/<owner>/<repo> --db .gitgraph/smoke.db
   ```

   Confirm:
   - [ ] It actually clones (you'll see git's clone progress, or at minimum
         a noticeable pause for a repo of any size).
   - [ ] It exits 0 and prints `gitgraph: wrote N commits from
         https://github.com/<owner>/<repo> to .gitgraph/smoke.db` with `N`
         non-zero and roughly matching what you'd expect from
         `git log --oneline | wc -l` on that repo.
   - [ ] A new directory appears at `.gitgraph/repos/<slug>/` containing a
         full (non-shallow), **bare/mirror** clone (`--mirror`, so it's a
         `HEAD`/`refs`/`objects` layout directly at that path, no `.git`
         subdirectory) — spot check with
         `git -C .gitgraph/repos/<slug> log --oneline | wc -l` and confirm
         it's *not* suspiciously small (a shallow clone would under-report
         history — ADR 0003 is explicit this must never happen).

3. Run the exact same command again:

   ```sh
   time gitgraph analyze https://github.com/<owner>/<repo> --db .gitgraph/smoke.db
   ```

   Confirm:
   - [ ] It's noticeably faster than step 2 (fetch, not a full re-clone) —
         eyeball the elapsed time, or confirm the cache dir itself wasn't
         recreated (e.g. `stat .gitgraph/repos/<slug>/HEAD` shows the same
         inode/creation time across both runs — `fetch --all` on a mirror
         clone updates `refs/heads/*` in place, unlike a plain clone, so
         this is also how you'd notice if upstream gained new commits: the
         branch tip in `.gitgraph/repos/<slug>/refs/heads/<default-branch>`
         moves without the file being recreated).
   - [ ] It still exits 0 and reports the same (or, if the upstream repo
         gained commits in the interim, a larger) commit count.

4. Confirm `meta.repo_path` recorded the URL, not the local cache path:

   ```sh
   sqlite3 .gitgraph/smoke.db "select repo_path from meta;"
   ```

   - [ ] Output is exactly `https://github.com/<owner>/<repo>` (whatever you
         passed on the command line), **not** a path under
         `.gitgraph/repos/`.

5. Serve the dashboard against that db:

   ```sh
   gitgraph serve --db .gitgraph/smoke.db
   ```

   Open `http://127.0.0.1:8000/` and confirm:
   - [ ] The repo identity shown on the page is the GitHub URL, not a local
         path.
   - [ ] Commits/contributors stats and the recent-commits list reflect the
         real remote repo's actual history (cross-check a few subjects/SHAs
         against the GitHub repo's commit list in a browser).

6. Bonus (optional) — confirm a bad URL fails cleanly rather than hanging or
   stack-tracing:

   ```sh
   gitgraph analyze https://github.com/this-owner-does-not-exist-xyz/nope --db /tmp/bad.db
   ```

   - [ ] Exits non-zero with a one-line `gitgraph: ...` stderr message
         (surfacing git's own clone failure), not a Python traceback.

## Known simplifications (not bugs)

- Auth for private repos is entirely delegated to your local git/SSH
  config (credential helper, SSH agent) — GitGraph does not prompt for or
  store credentials itself. If a private-repo clone fails, that's your git
  config to fix, not a GitGraph bug (ADR 0003).
- `.gitgraph/repos/` is a persistent cache, not a temp dir — it accumulates
  one full clone per distinct URL you've ever analyzed. It's `.gitignore`d;
  clean it up manually if disk space matters to you.
- This checklist requires real network access (cloning from GitHub) and is
  therefore not part of the CI-gating `test` job — see
  `tests/test_analyze_url.py` for the equivalent automated coverage against
  a local `file://` bare repo.
