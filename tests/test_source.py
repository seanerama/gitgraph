"""Unit tests for `gitgraph.source`'s URL-vs-local-path detection and the
local-path branch of `resolve_target` (unchanged behavior). The clone/fetch
branch is covered by the `file://` bare-repo integration tests in
`tests/test_analyze_url.py`, which need no real network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gitgraph import source


@pytest.mark.parametrize(
    "target",
    [
        "https://github.com/owner/repo.git",
        "https://github.com/owner/repo",
        "http://example.com/owner/repo.git",
        "git://example.com/owner/repo.git",
        "ssh://git@example.com/owner/repo.git",
        "file:///home/user/bare-repos/remote.git",
        "git@github.com:owner/repo.git",
        "git@example.com:group/sub/repo.git",
    ],
)
def test_is_url_recognizes_urls(target):
    assert source.is_url(target) is True


@pytest.mark.parametrize(
    "target",
    [
        ".",
        "..",
        "relative/path",
        "./relative/path",
        "../sibling/path",
        "/abs/path/to/repo",
        "/abs/path",
        "repo-name",
    ],
)
def test_is_url_treats_everything_else_as_local_path(target):
    assert source.is_url(target) is False


def test_resolve_target_local_path_returns_resolved_path_as_both_elements(tmp_path):
    repo = tmp_path / "some-repo"
    repo.mkdir()

    operative_path, display_identity = source.resolve_target(str(repo))

    assert operative_path == repo.resolve()
    assert display_identity == str(repo.resolve())


def test_resolve_target_local_relative_path_resolves_against_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "some-repo"
    repo.mkdir()
    monkeypatch.chdir(tmp_path)

    operative_path, display_identity = source.resolve_target("some-repo")

    assert operative_path == repo.resolve()
    assert display_identity == str(repo.resolve())


def test_resolve_target_dot_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    operative_path, display_identity = source.resolve_target(".")

    assert operative_path == tmp_path.resolve()
    assert display_identity == str(tmp_path.resolve())


def test_slug_for_url_is_deterministic_and_filesystem_safe():
    url = "https://github.com/owner/repo.git"
    slug1 = source._slug_for_url(url)
    slug2 = source._slug_for_url(url)

    assert slug1 == slug2
    assert all(c.isalnum() or c in "._-" for c in slug1)


def test_slug_for_url_differs_for_different_urls():
    slug_a = source._slug_for_url("https://github.com/owner/repo.git")
    slug_b = source._slug_for_url("https://github.com/owner/other.git")

    assert slug_a != slug_b
