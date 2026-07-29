"""Integration tests for gitgraph/api.py against contracts/dashboard-api.md
v1's `/api/summary` and `/api/commits` endpoints — the two implemented by
this stage. Reuses Stage 1's fixture-repo builder from
tests/test_integration.py rather than duplicating it.

Also covers the ADR 0002 security property that `gitgraph serve` binds
127.0.0.1 only, never 0.0.0.0.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from gitgraph.api import create_app
from gitgraph.cli import (
    SERVE_HOST,
    build_parser,
    build_uvicorn_config,
    main as cli_main,
)

from tests.test_integration import build_fixture_repo


@pytest.fixture
def analyzed_fixture(tmp_path):
    repo = tmp_path / "fixture-repo"
    info = build_fixture_repo(repo)
    db_path = tmp_path / "out" / "fixture-repo.db"
    exit_code = cli_main(["analyze", str(repo), "--db", str(db_path)])
    assert exit_code == 0
    return repo, info, db_path


# --- /api/summary -----------------------------------------------------


def test_summary_matches_fixture_repo(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/api/summary")
    assert resp.status_code == 200
    body = resp.json()

    assert body["repo_path"] == str(repo.resolve())
    assert body["head_sha"] == info["c6_merge"]
    assert body["commit_count"] == 6
    # the fixture builder uses a single author identity for every commit
    assert body["contributor_count"] == 1
    # no `snapshots` data yet (analyzer stage not built) — null is valid
    assert body["total_code_lines"] is None
    assert body["first_commit_at"]
    assert body["last_commit_at"]
    assert body["first_commit_at"] <= body["last_commit_at"]


def test_summary_errors_cleanly_on_unanalyzed_db(tmp_path):
    empty_db = tmp_path / "empty.db"
    client = TestClient(create_app(empty_db))

    resp = client.get("/api/summary")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["message"]
    assert body["error"]["code"]


# --- /api/commits -------------------------------------------------------


def test_commits_endpoint_matches_fixture_repo(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/api/commits")
    assert resp.status_code == 200
    body = resp.json()
    nodes = {n["sha"]: n for n in body["nodes"]}

    assert set(nodes.keys()) == info["all_shas"]

    merge_node = nodes[info["c6_merge"]]
    assert merge_node["parents"] == [info["c5_mainline"], info["c4_feature"]]
    assert set(merge_node["refs"]) == {"main", "v1.0"}
    assert merge_node["subject"] == "merge feature"
    assert merge_node["author_email"] == "fixture@example.com"

    root_node = nodes[info["c1"]]
    assert root_node["parents"] == []

    feature_node = nodes[info["c4_feature"]]
    assert feature_node["refs"] == ["feature"]

    non_merge_node = nodes[info["c2"]]
    assert non_merge_node["parents"] == [info["c1"]]


def test_commits_endpoint_filters_by_branch(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/api/commits", params={"branch": "feature"})
    assert resp.status_code == 200
    shas = {n["sha"] for n in resp.json()["nodes"]}
    # ancestors of the `feature` branch tip: c1 -> c2 -> c3_rename -> c4_feature
    assert shas == {info["c1"], info["c2"], info["c3_rename"], info["c4_feature"]}


def test_commits_endpoint_unknown_branch_errors(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/api/commits", params={"branch": "does-not-exist"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["message"]
    assert body["error"]["code"]


# --- static shell ---------------------------------------------------------


def test_index_page_served(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "gitgraph" in resp.text.lower()

    js_resp = client.get("/app.js")
    assert js_resp.status_code == 200
    assert "/api/summary" in js_resp.text


# --- Stage 4: D3 commit-graph static assets --------------------------------


def test_index_page_no_longer_has_placeholder_commit_list(analyzed_fixture):
    """Stage 2's plain <ul id="commits"> placeholder must be actually
    swapped out for the D3 graph panel, not left dead in the DOM alongside
    it."""
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/")
    assert resp.status_code == 200
    assert '<ul id="commits">' not in resp.text
    # the new graph container should be present in its place
    assert 'id="graph"' in resp.text


def test_vendored_d3_is_served(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/vendor/d3.v7.min.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"].lower()
    # sanity: a real D3 v7 bundle, not an empty stub
    assert len(resp.content) > 100_000
    assert b"d3" in resp.content


def test_graph_js_is_served(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    client = TestClient(create_app(db_path))

    resp = client.get("/graph.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"].lower()
    assert "/api/commits" in resp.text


# --- ADR 0002: bind 127.0.0.1 only, never 0.0.0.0 --------------------------


def test_serve_subcommand_has_no_host_flag():
    """The CLI must not expose a --host flag that could be used to bind
    0.0.0.0 — binding is hardcoded to 127.0.0.1 (ADR 0002)."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["serve", "--host", "0.0.0.0"])


def test_uvicorn_config_binds_127_0_0_1(analyzed_fixture):
    repo, info, db_path = analyzed_fixture
    config = build_uvicorn_config(db_path, port=8000)
    assert config.host == "127.0.0.1"
    assert config.host != "0.0.0.0"
    assert SERVE_HOST == "127.0.0.1"


def test_serve_actually_starts_and_answers_on_127_0_0_1(analyzed_fixture):
    """Real startup smoke test (not just config inspection): start a server
    built exactly the way `gitgraph serve` builds one, on an ephemeral free
    port, and confirm it answers on 127.0.0.1."""
    repo, info, db_path = analyzed_fixture

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    free_port = sock.getsockname()[1]
    sock.close()

    config = build_uvicorn_config(db_path, port=free_port)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 5
        last_exc = None
        resp = None
        while time.time() < deadline:
            try:
                resp = httpx.get(f"http://127.0.0.1:{free_port}/api/summary", timeout=0.5)
                break
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(0.1)
        if resp is None:
            pytest.fail(f"server did not become ready on 127.0.0.1:{free_port}: {last_exc}")
        assert resp.status_code == 200
        assert resp.json()["commit_count"] == 6
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_serve_cli_errors_when_db_missing(tmp_path, capsys):
    missing_db = tmp_path / "does-not-exist.db"
    exit_code = cli_main(["serve", "--db", str(missing_db)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "gitgraph analyze" in captured.err
