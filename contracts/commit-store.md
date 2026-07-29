# Contract: commit-store

- **Status:** frozen v1
- **Owner:** `extractor` + `analyzer` modules (writers); `api` module (reader)

## Exposes

A SQLite database file (path chosen by the caller, e.g. `.gitgraph/<slug>.db`)
populated by `gitgraph analyze <repo-path>`, containing the full commit graph,
per-file numstat, refs, and periodic LOC snapshots for one Git repository.
Any component with read access to the file may query it directly — there is no
network layer at this seam, just the schema below.

## Consumes

`extractor` consumes `git log --all --date-order --pretty=... --numstat` and
`git show-ref` output from the local Git CLI. `analyzer` consumes `scc --format
json` run against `git archive <sha>` snapshots. Neither consumes the other
contract (`dashboard-api`) — this is the layer underneath it.

## Schema / wire

SQLite, one file per analyzed repo. All timestamps stored as ISO 8601 strings
(`git log %aI` / `%cI` already emit this format — no reformatting needed).

```sql
-- Provenance / run metadata. Single row, upserted each `gitgraph analyze` run.
CREATE TABLE meta (
  repo_path      TEXT PRIMARY KEY,
  head_sha       TEXT NOT NULL,
  extracted_at   TEXT NOT NULL,   -- ISO 8601, wall-clock time of this run
  gitgraph_version TEXT NOT NULL,
  scc_version    TEXT             -- NULL if analyzer step was skipped
);

-- One row per commit, first-parent-agnostic (parents live in commit_parents).
CREATE TABLE commits (
  sha            TEXT PRIMARY KEY,
  author_name    TEXT NOT NULL,
  author_email   TEXT NOT NULL,
  committer_name TEXT NOT NULL,
  committer_email TEXT NOT NULL,
  authored_at    TEXT NOT NULL,   -- ISO 8601
  committed_at   TEXT NOT NULL,   -- ISO 8601
  subject        TEXT NOT NULL,
  body           TEXT NOT NULL DEFAULT ''
);

-- Parent edges — reconstructs the DAG. parent_order 0 = first parent
-- (mainline for merge commits), 1+ = merged-in parents.
CREATE TABLE commit_parents (
  child_sha      TEXT NOT NULL REFERENCES commits(sha),
  parent_sha     TEXT NOT NULL,   -- not FK-enforced: parent may be outside
                                   -- a shallow/partial extraction range
  parent_order   INTEGER NOT NULL,
  PRIMARY KEY (child_sha, parent_order)
);

-- Branches and tags, resolved at extraction time. Re-extraction replaces
-- all rows (refs move; this table is a snapshot, not history of ref moves).
CREATE TABLE refs (
  name           TEXT NOT NULL,
  type           TEXT NOT NULL CHECK (type IN ('branch', 'tag')),
  target_sha     TEXT NOT NULL,
  PRIMARY KEY (name, type)
);

-- Per-file numstat for each commit. additions/deletions NULL for binary files.
CREATE TABLE file_changes (
  commit_sha     TEXT NOT NULL REFERENCES commits(sha),
  file_path      TEXT NOT NULL,
  additions      INTEGER,
  deletions      INTEGER,
  is_binary      INTEGER NOT NULL DEFAULT 0,  -- 0/1
  change_type    TEXT NOT NULL CHECK (change_type IN
                    ('add', 'delete', 'modify', 'rename', 'copy')),
  old_path       TEXT,            -- non-NULL only for rename/copy
  PRIMARY KEY (commit_sha, file_path)
);

-- Periodic codebase-size snapshots (scc), one row per language per sampled
-- commit. Sampling policy (every commit / daily / tags-only) lives in the
-- analyzer, not this schema — this table just holds whatever was sampled.
CREATE TABLE snapshots (
  commit_sha     TEXT NOT NULL REFERENCES commits(sha),
  snapshot_date  TEXT NOT NULL,   -- ISO 8601, the commit's committed_at
  language       TEXT NOT NULL,
  code_lines     INTEGER NOT NULL,
  comment_lines  INTEGER NOT NULL,
  blank_lines    INTEGER NOT NULL,
  file_count     INTEGER NOT NULL,
  PRIMARY KEY (commit_sha, language)
);

CREATE INDEX idx_commits_committed_at ON commits(committed_at);
CREATE INDEX idx_commit_parents_parent ON commit_parents(parent_sha);
CREATE INDEX idx_file_changes_path ON file_changes(file_path);
CREATE INDEX idx_snapshots_date ON snapshots(snapshot_date);
```

Contributors, churn, hotspot, and ownership metrics are **derived** from
`commits` + `file_changes` at query time (by `api`, or ad hoc) — they are not
separate tables in v1. If a derived metric becomes expensive enough to need
materialization, that's an additive migration (new table), not a change to
the tables above.

## Versioning

Frozen at **v1**. Changes are **additive only** — a breaking change is a NEW
contract, not an edit (framework-spec §4.3). Every consumer depends on this
shape. Concretely: new tables and new nullable columns are fine; renaming or
removing a column, or changing a column's meaning, is not — ship a new
contract (e.g. `commit-store-v2`) instead.
