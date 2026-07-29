"""SQLite storage layer for the `commit-store` v1 schema.

The DDL below is copied verbatim from `contracts/commit-store.md` (frozen
v1). Do not edit table/column names or types here without first revising
that contract — this module and the contract must always agree.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Verbatim from contracts/commit-store.md (frozen v1), with `IF NOT EXISTS`
# added to each statement so re-running analyze() against an existing db is
# idempotent — table/column names, types, and constraints are unchanged.
SCHEMA_DDL = """
-- Provenance / run metadata. Single row, upserted each `gitgraph analyze` run.
CREATE TABLE IF NOT EXISTS meta (
  repo_path      TEXT PRIMARY KEY,
  head_sha       TEXT NOT NULL,
  extracted_at   TEXT NOT NULL,   -- ISO 8601, wall-clock time of this run
  gitgraph_version TEXT NOT NULL,
  scc_version    TEXT             -- NULL if analyzer step was skipped
);

-- One row per commit, first-parent-agnostic (parents live in commit_parents).
CREATE TABLE IF NOT EXISTS commits (
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
CREATE TABLE IF NOT EXISTS commit_parents (
  child_sha      TEXT NOT NULL REFERENCES commits(sha),
  parent_sha     TEXT NOT NULL,   -- not FK-enforced: parent may be outside
                                   -- a shallow/partial extraction range
  parent_order   INTEGER NOT NULL,
  PRIMARY KEY (child_sha, parent_order)
);

-- Branches and tags, resolved at extraction time. Re-extraction replaces
-- all rows (refs move; this table is a snapshot, not history of ref moves).
CREATE TABLE IF NOT EXISTS refs (
  name           TEXT NOT NULL,
  type           TEXT NOT NULL CHECK (type IN ('branch', 'tag')),
  target_sha     TEXT NOT NULL,
  PRIMARY KEY (name, type)
);

-- Per-file numstat for each commit. additions/deletions NULL for binary files.
CREATE TABLE IF NOT EXISTS file_changes (
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
CREATE TABLE IF NOT EXISTS snapshots (
  commit_sha     TEXT NOT NULL REFERENCES commits(sha),
  snapshot_date  TEXT NOT NULL,   -- ISO 8601, the commit's committed_at
  language       TEXT NOT NULL,
  code_lines     INTEGER NOT NULL,
  comment_lines  INTEGER NOT NULL,
  blank_lines    INTEGER NOT NULL,
  file_count     INTEGER NOT NULL,
  PRIMARY KEY (commit_sha, language)
);

CREATE INDEX IF NOT EXISTS idx_commits_committed_at ON commits(committed_at);
CREATE INDEX IF NOT EXISTS idx_commit_parents_parent ON commit_parents(parent_sha);
CREATE INDEX IF NOT EXISTS idx_file_changes_path ON file_changes(file_path);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(snapshot_date);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating parent dirs and the schema if needed) a connection to
    the commit-store SQLite file at `db_path`."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the commit-store v1 tables/indexes if they don't already exist."""
    conn.executescript(SCHEMA_DDL)
    conn.commit()


def open_db(db_path: str | Path) -> sqlite3.Connection:
    """Convenience: connect + ensure schema exists, return the connection."""
    conn = connect(db_path)
    init_schema(conn)
    return conn
