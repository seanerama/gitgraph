"""Integration test: build a small real Git repo (via subprocess `git`
calls) with a merge commit and a renamed file, run `gitgraph analyze`
against it, and assert directly against the resulting SQLite file.

This is the project's first pipeline test (fixture repo -> gitgraph analyze
-> assert SQLite contents) per the stage spec.
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from gitgraph import __version__ as GITGRAPH_VERSION
from gitgraph.cli import main as cli_main


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def build_fixture_repo(repo: Path) -> dict:
    """Build a small real repo with a rename and a merge commit. Returns a
    dict of interesting shas/names for assertions."""
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.name", "Fixture Author")
    run_git(repo, "config", "user.email", "fixture@example.com")

    (repo / "a.txt").write_text("hello\n")
    run_git(repo, "add", "a.txt")
    run_git(repo, "commit", "-q", "-m", "first commit", "-m", "A body.\n\nWith a blank line.")
    c1 = run_git(repo, "rev-parse", "HEAD")

    (repo / "a.txt").write_text("hello\nmore\n")
    run_git(repo, "commit", "-q", "-am", "second commit")
    c2 = run_git(repo, "rev-parse", "HEAD")

    run_git(repo, "mv", "a.txt", "b.txt")
    (repo / "b.txt").write_text("hello\nmore\nextra\n")
    run_git(repo, "commit", "-q", "-am", "rename a to b")
    c3_rename = run_git(repo, "rev-parse", "HEAD")

    run_git(repo, "checkout", "-q", "-b", "feature")
    (repo / "c.txt").write_text("feature file\n")
    run_git(repo, "add", "c.txt")
    run_git(repo, "commit", "-q", "-m", "feature commit")
    c4_feature = run_git(repo, "rev-parse", "HEAD")

    run_git(repo, "checkout", "-q", "main")
    (repo / "d.txt").write_text("mainline file\n")
    run_git(repo, "add", "d.txt")
    run_git(repo, "commit", "-q", "-m", "mainline commit")
    c5_mainline = run_git(repo, "rev-parse", "HEAD")

    run_git(repo, "merge", "-q", "--no-ff", "feature", "-m", "merge feature")
    c6_merge = run_git(repo, "rev-parse", "HEAD")

    run_git(repo, "tag", "v1.0")

    return {
        "c1": c1,
        "c2": c2,
        "c3_rename": c3_rename,
        "c4_feature": c4_feature,
        "c5_mainline": c5_mainline,
        "c6_merge": c6_merge,
        "all_shas": {c1, c2, c3_rename, c4_feature, c5_mainline, c6_merge},
    }


@pytest.fixture
def fixture_repo(tmp_path):
    repo = tmp_path / "fixture-repo"
    info = build_fixture_repo(repo)
    return repo, info


def test_analyze_cli_produces_populated_db(fixture_repo, tmp_path):
    repo, info = fixture_repo
    db_path = tmp_path / "out" / "fixture-repo.db"

    exit_code = cli_main(["analyze", str(repo), "--db", str(db_path)])

    assert exit_code == 0
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # --- commit count: exact, non-zero (CLI-smoke condition) ---
        (commit_count,) = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
        assert commit_count == 6
        assert commit_count == len(info["all_shas"])

        db_shas = {row["sha"] for row in conn.execute("SELECT sha FROM commits")}
        assert db_shas == info["all_shas"]

        # --- merge commit parent edges, parent_order preserved ---
        parent_rows = conn.execute(
            "SELECT parent_sha, parent_order FROM commit_parents "
            "WHERE child_sha = ? ORDER BY parent_order",
            (info["c6_merge"],),
        ).fetchall()
        assert [r["parent_order"] for r in parent_rows] == [0, 1]
        assert parent_rows[0]["parent_sha"] == info["c5_mainline"]
        assert parent_rows[1]["parent_sha"] == info["c4_feature"]

        # non-merge commits have exactly one parent at order 0
        c2_parents = conn.execute(
            "SELECT parent_sha, parent_order FROM commit_parents WHERE child_sha = ?",
            (info["c2"],),
        ).fetchall()
        assert len(c2_parents) == 1
        assert c2_parents[0]["parent_order"] == 0
        assert c2_parents[0]["parent_sha"] == info["c1"]

        # root commit has no parents
        c1_parents = conn.execute(
            "SELECT * FROM commit_parents WHERE child_sha = ?", (info["c1"],)
        ).fetchall()
        assert c1_parents == []

        # --- rename detection ---
        rename_row = conn.execute(
            "SELECT file_path, old_path, change_type, is_binary FROM file_changes "
            "WHERE commit_sha = ? AND file_path = 'b.txt'",
            (info["c3_rename"],),
        ).fetchone()
        assert rename_row is not None
        assert rename_row["change_type"] == "rename"
        assert rename_row["old_path"] == "a.txt"
        assert rename_row["is_binary"] == 0

        # the rename commit should not also carry a stray a.txt row
        stray = conn.execute(
            "SELECT * FROM file_changes WHERE commit_sha = ? AND file_path = 'a.txt'",
            (info["c3_rename"],),
        ).fetchall()
        assert stray == []

        # --- plain add rows look right ---
        add_row = conn.execute(
            "SELECT change_type, old_path, additions, deletions FROM file_changes "
            "WHERE commit_sha = ? AND file_path = 'a.txt'",
            (info["c1"],),
        ).fetchone()
        assert add_row["change_type"] == "add"
        assert add_row["old_path"] is None
        assert add_row["additions"] == 1
        assert add_row["deletions"] == 0

        # --- refs: branch + tag names and targets ---
        refs = {(r["name"], r["type"]): r["target_sha"] for r in conn.execute("SELECT * FROM refs")}
        assert refs[("main", "branch")] == info["c6_merge"]
        assert refs[("feature", "branch")] == info["c4_feature"]
        assert refs[("v1.0", "tag")] == info["c6_merge"]

        # --- meta row ---
        meta = conn.execute("SELECT * FROM meta").fetchone()
        assert meta is not None
        assert meta["head_sha"] == info["c6_merge"]
        assert meta["gitgraph_version"] == GITGRAPH_VERSION
        assert meta["repo_path"] == str(repo.resolve())
        assert meta["extracted_at"]  # non-empty ISO timestamp

        # snapshots table is explicitly out of scope for this stage
        (snapshot_count,) = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()
        assert snapshot_count == 0
    finally:
        conn.close()


def test_analyze_default_db_path(fixture_repo, tmp_path, monkeypatch):
    repo, info = fixture_repo
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    exit_code = cli_main(["analyze", str(repo)])

    assert exit_code == 0
    expected_db = workdir / ".gitgraph" / f"{repo.name}.db"
    assert expected_db.exists()

    conn = sqlite3.connect(str(expected_db))
    try:
        (commit_count,) = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
        assert commit_count == 6
    finally:
        conn.close()


def test_analyze_is_rerunnable_and_replaces_rows(fixture_repo, tmp_path):
    repo, info = fixture_repo
    db_path = tmp_path / "rerun.db"

    assert cli_main(["analyze", str(repo), "--db", str(db_path)]) == 0
    assert cli_main(["analyze", str(repo), "--db", str(db_path)]) == 0

    conn = sqlite3.connect(str(db_path))
    try:
        (commit_count,) = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
        assert commit_count == 6
        (meta_count,) = conn.execute("SELECT COUNT(*) FROM meta").fetchone()
        assert meta_count == 1
    finally:
        conn.close()


def test_analyze_rejects_non_git_directory(tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    exit_code = cli_main(["analyze", str(not_a_repo), "--db", str(tmp_path / "out.db")])
    assert exit_code == 1
