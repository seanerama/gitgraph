"""Resolves an `analyze` CLI target — a local filesystem path or a Git URL —
into a local path the (unmodified) extractor can operate on, per ADR 0003
(`docs/adr/0003-support-analyzing-a-remote-repo-by-url.md`).

Detection is a simple prefix/pattern check on the target string, never a
network probe. Local paths behave exactly as before this stage. URLs are
cloned (first time) or fetched (subsequent times) into a deterministic,
persistent cache directory under `.gitgraph/repos/<slug>/` — never a
shallow clone, per ADR 0003's explicit rejection of `--depth`/
`--shallow-since` (a shallow clone silently corrupts GitGraph's core
metrics).

Auth is delegated entirely to the operator's own git/SSH configuration —
this module does not implement or store any credentials; it just shells
out to `git clone`/`git fetch`, the same "boring subprocess" approach as
`gitgraph/extractor.py` (ADR 0001).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from .extractor import GitError

# ADR 0003: https://, http://, git:// prefixes, or git@host:owner/repo.git
# SSH scp-like syntax count as URLs. ssh:// and file:// are also real git
# URL schemes and are included for completeness — file:// in particular is
# how this stage's own tests exercise the real clone/fetch codepath without
# any network I/O (a local `git init --bare` "remote" addressed via its
# file:// URL). Everything else is a local path.
_URL_PREFIXES = ("https://", "http://", "git://", "ssh://", "file://")
_SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:.+$")

DEFAULT_REPOS_ROOT = Path(".gitgraph") / "repos"


def is_url(target: str) -> bool:
    """True if `target` looks like a Git URL (per ADR 0003's detection
    rules), false if it should be treated as a local filesystem path."""
    if target.startswith(_URL_PREFIXES):
        return True
    return bool(_SCP_LIKE_RE.match(target))


def _slug_for_url(url: str) -> str:
    """Deterministic, filesystem-safe, stable-across-runs slug for `url`.

    Keeps a readable prefix (host/owner/repo with unsafe characters
    collapsed to `-`) plus a short hash suffix so distinct URLs that
    happen to sanitize to the same readable string never collide.
    """
    stripped = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)  # drop scheme
    stripped = re.sub(r"^[^@/]+@", "", stripped)  # drop scp-style user@
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stripped).strip("-")
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{safe}-{digest}" if safe else digest


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _looks_like_git_dir(path: Path) -> bool:
    return (path / ".git").exists() or (path / "HEAD").exists()


def resolve_target(
    target: str, *, repos_root: str | Path = DEFAULT_REPOS_ROOT
) -> tuple[Path, str]:
    """Resolve an `analyze` target to `(operative_path, display_identity)`.

    - Local path: returned as-is, resolved — identical behavior to before
      this stage. `operative_path == display_identity` (both the resolved
      path).
    - URL: clones into (first run) or fetches (subsequent runs) a
      deterministic cache dir under `repos_root/<slug>/`, always a full
      clone (never `--depth`/`--shallow-since` — ADR 0003). Returns the
      cache dir as `operative_path` and the original `target` string,
      unchanged, as `display_identity` — this is what callers should record
      in `meta.repo_path` so a URL-sourced db is self-describing.

    Raises `GitError` (same class the extractor raises) if the underlying
    `git clone`/`git fetch` subprocess fails, with that subprocess's stderr
    included cleanly in the message.
    """
    if not is_url(target):
        resolved = Path(target).resolve()
        return resolved, str(resolved)

    slug = _slug_for_url(target)
    cache_dir = Path(repos_root) / slug

    if _looks_like_git_dir(cache_dir):
        result = _run_git(["-C", str(cache_dir), "fetch", "--all"])
        if result.returncode != 0:
            raise GitError(
                f"git fetch --all failed for {target} (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
    else:
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        # --mirror (not a plain clone): a plain clone's subsequent `fetch
        # --all` only updates refs/remotes/origin/* — refs/heads/* (and
        # therefore HEAD) stay pinned to whatever they were at clone time,
        # so meta.head_sha and the refs table would silently go stale on
        # every re-analysis. A mirror clone's refspec is `+refs/*:refs/*`,
        # so `fetch --all` updates refs/heads/* directly — verified this is
        # necessary and sufficient (see docs/adr/0003 discussion). Still a
        # full clone, never shallow, per ADR 0003.
        result = _run_git(["clone", "--mirror", target, str(cache_dir)])
        if result.returncode != 0:
            raise GitError(
                f"git clone {target} failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

    return cache_dir.resolve(), target
