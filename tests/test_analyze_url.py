"""Integration tests for `gitgraph analyze <url>` (Stage 3 / ADR 0003),
exercised against a local `git init --bare` "remote" via a `file://` URL —
a real git URL scheme that needs zero real network access.

Covers: first run clones into the cache dir; second run fetches (does not
re-clone) and picks up new commits; `meta.repo_path` stores the original
URL, not the local cache path; a bad/unreachable URL fails cleanly (exit 1,
stderr message, no traceback).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gitgraph import source
from gitgraph.cli import main as cli_main
from tests.test_integration import build_fixture_repo, run_git


def build_bare_remote(tmp_path: Path) -> tuple[Path, Path, dict]:
    """Build a small bare repo (the "remote") and a throwaway working clone
    that pushes GitGraph's usual fixture history (merge commit + rename)
    into it. Returns (bare_repo_path, working_clone_path, fixture_info)."""
    bare = tmp_path / "remote.git"
    run_git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))

    work = tmp_path / "work"
    info = build_fixture_repo(work)
    run_git(work, "remote", "add", "origin", str(bare))
    run_git(work, "push", "-q", "origin", "--all")
    run_git(work, "push", "-q", "origin", "--tags")

    return bare, work, info


def test_analyze_url_clones_on_first_run(tmp_path, monkeypatch):
    bare, work, info = build_bare_remote(tmp_path)
    target = bare.as_uri()

    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    db_path = workdir / "out.db"

    exit_code = cli_main(["analyze", target, "--db", str(db_path)])
    assert exit_code == 0

    slug = source._slug_for_url(target)
    cache_dir = workdir / ".gitgraph" / "repos" / slug
    # A --mirror clone is bare: HEAD/refs live directly at the cache dir
    # root, there is no .git subdirectory (see ADR 0003 discussion in
    # source.py on why --mirror, not a plain clone).
    assert (cache_dir / "HEAD").exists()
    assert not (cache_dir / ".git").exists()

    conn = sqlite3.connect(str(db_path))
    try:
        (commit_count,) = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
        assert commit_count == len(info["all_shas"])
        assert commit_count == 6

        meta = conn.execute("SELECT repo_path, head_sha FROM meta").fetchone()
        assert meta is not None
        # Per ADR 0003: meta.repo_path stores the original URL target, not
        # the local .gitgraph/repos/<slug> cache path.
        assert meta[0] == target
        assert meta[0] != str(cache_dir)
        assert meta[1] == info["c6_merge"]
    finally:
        conn.close()


def test_analyze_url_second_run_fetches_not_reclones_and_picks_up_new_commits(
    tmp_path, monkeypatch
):
    bare, work, info = build_bare_remote(tmp_path)
    target = bare.as_uri()

    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    db_path = workdir / "out.db"

    assert cli_main(["analyze", target, "--db", str(db_path)]) == 0

    slug = source._slug_for_url(target)
    cache_dir = workdir / ".gitgraph" / "repos" / slug
    # A --mirror clone is bare (no .git subdir); confirm it exists.
    assert (cache_dir / "HEAD").exists()
    # Check the *directory's own* inode, not a file inside it: `git fetch`
    # can atomically rewrite individual ref files (write-temp-then-rename),
    # which changes THEIR inode even on a legitimate fetch — that's not a
    # reliable signal and is git-version/filesystem dependent (this exact
    # check against HEAD's own inode passed locally but flaked in CI). The
    # containing directory's inode is untouched by any file-level rewrite
    # inside it; only a genuine delete-and-reclone (e.g. a naive
    # `rm -rf` + `git clone` "cache invalidation") would recreate the
    # directory itself.
    inode_before = cache_dir.stat().st_ino

    # Add a new commit to the "remote" between runs.
    (work / "new.txt").write_text("more content\n")
    run_git(work, "add", "new.txt")
    run_git(work, "commit", "-q", "-m", "extra commit after first analyze")
    run_git(work, "push", "-q", "origin", "main")
    new_head = run_git(work, "rev-parse", "HEAD")

    assert cli_main(["analyze", target, "--db", str(db_path)]) == 0

    # Cache dir was reused (fetch), not recreated (re-clone).
    inode_after = cache_dir.stat().st_ino
    assert inode_after == inode_before

    conn = sqlite3.connect(str(db_path))
    try:
        (commit_count,) = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
        # The extra commit only reaches this repo via the fetched
        # refs/remotes/origin/main ref, which `git log --all` includes —
        # this only works if the second run fetched rather than skipped.
        assert commit_count == len(info["all_shas"]) + 1

        meta = conn.execute("SELECT repo_path, head_sha FROM meta").fetchone()
        assert meta[0] == target
        # Regression check: a plain `git clone` + `fetch --all` leaves
        # refs/heads/* (and therefore HEAD) pinned to the first run's tip —
        # only refs/remotes/origin/* updates. meta.head_sha and the refs
        # table would then silently go stale on every re-analysis. The
        # cache is a --mirror clone specifically so this stays correct.
        assert meta[1] == new_head

        main_ref = conn.execute(
            "SELECT target_sha FROM refs WHERE name = 'main' AND type = 'branch'"
        ).fetchone()
        assert main_ref is not None
        assert main_ref[0] == new_head
    finally:
        conn.close()


def test_analyze_bad_url_fails_cleanly(tmp_path, monkeypatch, capsys):
    nonexistent = tmp_path / "does-not-exist"
    target = nonexistent.as_uri()

    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    db_path = workdir / "out.db"

    exit_code = cli_main(["analyze", target, "--db", str(db_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "gitgraph:" in captured.err
    assert not db_path.exists()
