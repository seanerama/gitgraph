Yes. Git contains enough information to build both a **commit-history graph** and a set of **codebase metrics over time**.

The result could look like a repository “health timeline”:

* Top panel: branches, commits, merges, tags, and releases.
* Middle panel: total lines of code by language.
* Bottom panels: additions/deletions, contributors, file churn, tests, complexity, and other metrics.
* Shared time selector: zooming into a period updates every panel.

## What you can extract

### Directly from Git

Git provides:

* Commit timestamp
* Author and committer
* Parent commits
* Branch and merge relationships
* Files changed
* Lines added and deleted
* Tags
* Commit messages
* File history
* Renames and deletions

A basic source command would be something like:

```bash
git log \
  --all \
  --date-order \
  --pretty=format:'%H|%P|%aI|%an|%ae|%s' \
  --numstat
```

The important fields are:

* `%H`: commit hash
* `%P`: parent hashes
* `%aI`: author timestamp
* `%an`: author name
* `%s`: commit subject
* `--numstat`: additions and deletions by file

The parent hashes let you reconstruct the actual Git directed acyclic graph, including branches and merges.

## Lines of code over time

There are two different measurements worth separating.

### Code churn

Git can calculate this efficiently:

```text
additions
deletions
net change
files changed
```

For example:

```bash
git diff-tree \
  --no-commit-id \
  --numstat \
  -r <commit>
```

This tells you how much changed in each commit, but it does **not necessarily tell you the exact size of the codebase** at that point.

### Codebase size

For accurate lines of code, periodically analyze the repository snapshot at a commit using:

* `scc`
* `tokei`
* `cloc`

Conceptually:

```bash
git archive <commit> | analyze-with-scc-or-tokei
```

You probably would not need to analyze every commit. A practical approach is:

* Analyze every commit for small repositories.
* Analyze one snapshot per day or week for medium repositories.
* Analyze tags, releases, and weekly snapshots for large repositories.

This produces measurements such as:

```text
date
commit_sha
language
code_lines
comment_lines
blank_lines
file_count
```

## Other useful statistics

A strong first version could include:

| Metric                         | What it reveals                      |
| ------------------------------ | ------------------------------------ |
| Commits over time              | Development pace                     |
| Additions and deletions        | Change volume                        |
| Net LOC                        | Codebase growth                      |
| Code churn                     | Reworked or unstable areas           |
| Files changed per commit       | Scope of changes                     |
| Contributors over time         | Team participation                   |
| First-time contributors        | Community growth                     |
| Merge frequency                | Branching and collaboration patterns |
| Commit size distribution       | Whether changes are small or risky   |
| File age                       | Old or potentially neglected code    |
| Hotspot files                  | Files repeatedly changed             |
| Ownership concentration        | Files dependent on one contributor   |
| Language composition           | Architecture evolution               |
| Test LOC versus production LOC | Testing investment                   |
| Release cadence                | Delivery frequency                   |
| Time between releases          | Project maturity and velocity        |

More advanced analysis could add:

* Cyclomatic or cognitive complexity over time
* Dependency count and dependency freshness
* Security findings over time
* Test counts and test execution results
* Build duration and CI success rate
* Documentation-to-code ratio
* Conventional commit categories
* Feature, fix, refactor, and documentation activity
* Pull request cycle time
* Issue-to-commit relationships

Git alone cannot supply all of those. CI, pull request, issue, and release information would normally come from the GitHub or GitLab API.

## Recommended visualization

I would avoid drawing the Git graph and LOC line directly on the same axis. Their scales and structures are too different.

A better interface would have synchronized panels:

```text
┌─────────────────────────────────────────────────────┐
│ Repository summary                                  │
│ 2,481 commits · 19 contributors · 87,200 LOC        │
├─────────────────────────────────────────────────────┤
│ Commit graph                                        │
│ main ─●─●──────●──────●────────●──────●             │
│          ╲    ╱        ╲       ╱                     │
│ feature   ●──●          ●─●───●                      │
├─────────────────────────────────────────────────────┤
│ Lines of code                                       │
│        ╭──────────────╮                              │
│   ─────╯              ╰────────────                  │
├─────────────────────────────────────────────────────┤
│ Additions / deletions / churn                       │
│ ▂▅▃▁▇▂▂▁▆▃▁▂▇▂                                      │
├─────────────────────────────────────────────────────┤
│ Releases, contributors, languages, hotspots         │
└─────────────────────────────────────────────────────┘
```

Hovering over a commit could show:

* Commit message
* Author
* Date and time
* Branch
* Parent commits
* Files changed
* Additions and deletions
* LOC after the commit
* Associated pull request or issue
* Whether CI passed

## Suggested architecture

A straightforward implementation could use:

```text
Git repository
      │
      ├── Commit extractor
      │     ├── metadata
      │     ├── parent relationships
      │     └── file-level numstat
      │
      ├── Snapshot analyzer
      │     ├── scc / tokei / cloc
      │     ├── language statistics
      │     └── optional complexity analysis
      │
      ├── GitHub/GitLab enricher
      │     ├── pull requests
      │     ├── issues
      │     ├── releases
      │     └── CI results
      │
      ▼
SQLite or DuckDB
      │
      ▼
Interactive web dashboard
```

For a local, portable application, I would use:

* **Python** for extraction
* **PyDriller** or Git CLI subprocesses for walking history
* **scc** for code statistics
* **DuckDB or SQLite** for storage
* **Plotly** for metric charts
* **D3.js** or a specialized graph layout for the commit DAG
* **FastAPI** only if the dashboard needs a backend

## Important limitations

Lines of code should be treated as descriptive rather than as a productivity metric. A commit deleting 20,000 unnecessary lines may be more valuable than one adding 20,000.

You would also want configuration for excluding:

```text
vendor/
node_modules/
dist/
build/
migrations/
generated files
lock files
minified assets
test fixtures
```

Other complications include:

* Shallow clones missing old history
* Rewritten or rebased history
* Squash merges hiding intermediate commits
* Author aliases producing duplicate contributors
* Binary files
* Large generated commits
* Renames being interpreted as deletion plus addition
* Multiple branches containing commits that never reached the default branch

For your earlier interactive project-history idea, this would be a natural evolution: instead of manually maintaining phases, the application could derive the factual development timeline from Git, then let you add human-authored annotations explaining **why** major architectural changes happened.

