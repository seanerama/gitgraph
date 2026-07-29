"""FastAPI app implementing the frozen `dashboard-api` v1 contract (see
`contracts/dashboard-api.md`) — this stage builds only `/api/summary` and
`/api/commits`; `/api/metrics/loc` and `/api/metrics/churn` are explicitly
out of scope until a later stage (they depend on `snapshots` data the
`analyzer` module doesn't populate yet).

Read-only consumer of the `commit-store` v1 schema (`contracts/commit-store.md`)
via `gitgraph.storage`'s connection helper — no independent schema
interpretation happens here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import storage

WEB_DIR = Path(__file__).parent / "web"

# Ancestor closure of a branch's target sha, walked over `commit_parents`
# (all parent edges, not just first-parent — a merge commit's ancestors
# include everything reachable through either parent). This is the
# "reasonable interpretation" of branch-filtering the stage spec calls for:
# the schema only stores a ref -> sha snapshot, not full branch membership
# history, so "commits on a branch" is defined here as "commits reachable
# from that branch's current tip."
_ANCESTORS_OF_SQL = """
WITH RECURSIVE anc(sha) AS (
    SELECT ?
    UNION
    SELECT cp.parent_sha FROM commit_parents cp JOIN anc ON cp.child_sha = anc.sha
)
SELECT sha FROM anc
"""


def _error(status_code: int, message: str, code: str) -> JSONResponse:
    """Build the frozen dashboard-api error envelope:
    {"error": {"message": str, "code": str}}."""
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "code": code}})


def create_app(db_path: str | Path) -> FastAPI:
    """Build the gitgraph dashboard FastAPI app, reading from the
    commit-store SQLite file at `db_path`. Also serves the static `web`
    shell (index.html + app.js) at `/`."""
    db_path = Path(db_path)
    app = FastAPI(title="gitgraph dashboard api")
    app.state.db_path = db_path

    def _conn() -> sqlite3.Connection:
        conn = storage.open_db(app.state.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @app.get("/api/summary")
    def get_summary():
        conn = _conn()
        try:
            meta = conn.execute("SELECT repo_path, head_sha FROM meta LIMIT 1").fetchone()
            if meta is None:
                return _error(
                    404,
                    "no analyzed repo found in this commit-store db — run `gitgraph analyze` first",
                    "not_found",
                )
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS commit_count,
                    COUNT(DISTINCT author_email) AS contributor_count,
                    MIN(authored_at) AS first_commit_at,
                    MAX(authored_at) AS last_commit_at
                FROM commits
                """
            ).fetchone()
            return {
                "repo_path": meta["repo_path"],
                "head_sha": meta["head_sha"],
                "commit_count": totals["commit_count"],
                "contributor_count": totals["contributor_count"],
                # No `snapshots` data until the analyzer stage exists yet —
                # null is a valid, additive-compatible partial response per
                # the contract, not a violation.
                "total_code_lines": None,
                "first_commit_at": totals["first_commit_at"],
                "last_commit_at": totals["last_commit_at"],
            }
        finally:
            conn.close()

    @app.get("/api/commits")
    def get_commits(
        since: Optional[str] = Query(None, description="ISO 8601 date, inclusive lower bound on authored_at"),
        until: Optional[str] = Query(None, description="ISO 8601 date, inclusive upper bound on authored_at"),
        branch: Optional[str] = Query(None, description="ref name; filters to that branch's ancestor commits"),
    ):
        conn = _conn()
        try:
            allowed_shas: Optional[set[str]] = None
            if branch is not None:
                ref_row = conn.execute(
                    "SELECT target_sha FROM refs WHERE name = ? AND type = 'branch'",
                    (branch,),
                ).fetchone()
                if ref_row is None:
                    return _error(404, f"unknown branch: {branch!r}", "not_found")
                allowed_shas = {
                    row["sha"] for row in conn.execute(_ANCESTORS_OF_SQL, (ref_row["target_sha"],))
                }

            query = "SELECT sha, author_name, author_email, authored_at, subject FROM commits"
            clauses = []
            params: list[str] = []
            if since is not None:
                clauses.append("authored_at >= ?")
                params.append(since)
            if until is not None:
                clauses.append("authored_at <= ?")
                params.append(until)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY authored_at DESC"

            commit_rows = conn.execute(query, params).fetchall()
            if allowed_shas is not None:
                commit_rows = [row for row in commit_rows if row["sha"] in allowed_shas]

            shas = [row["sha"] for row in commit_rows]
            parents_by_sha: dict[str, list[str]] = {sha: [] for sha in shas}
            refs_by_sha: dict[str, list[str]] = {sha: [] for sha in shas}
            if shas:
                placeholders = ",".join("?" * len(shas))
                for row in conn.execute(
                    f"SELECT child_sha, parent_sha FROM commit_parents "
                    f"WHERE child_sha IN ({placeholders}) ORDER BY child_sha, parent_order",
                    shas,
                ):
                    parents_by_sha[row["child_sha"]].append(row["parent_sha"])
                for row in conn.execute(
                    f"SELECT name, target_sha FROM refs WHERE target_sha IN ({placeholders})",
                    shas,
                ):
                    refs_by_sha[row["target_sha"]].append(row["name"])

            nodes = [
                {
                    "sha": row["sha"],
                    "parents": parents_by_sha.get(row["sha"], []),
                    "author_name": row["author_name"],
                    "author_email": row["author_email"],
                    "authored_at": row["authored_at"],
                    "subject": row["subject"],
                    "refs": refs_by_sha.get(row["sha"], []),
                }
                for row in commit_rows
            ]
            return {"nodes": nodes}
        finally:
            conn.close()

    # Static shell (index.html + app.js) — mounted last so it never shadows
    # the /api/* routes defined above.
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app
