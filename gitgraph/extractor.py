"""Extracts commit history from a local Git repository into the
`commit-store` v1 schema (see `contracts/commit-store.md`).

Design notes on the git invocations used here (see also the module-level
comments below): plain `git log --numstat` cannot reliably distinguish
add/modify/delete/rename/copy for a changed path — numstat alone only gives
line counts plus an ambiguous "old => new" arrow notation for renames/copies
that requires fragile brace-expansion parsing and still can't tell a rename
from a copy. Instead we combine `--numstat` with `--raw` (plus `-M -C` to
enable rename/copy detection) in a single `git log` invocation. Empirically
(verified against git 2.43), git emits, per commit, the block of `--raw`
lines followed by the block of `--numstat` lines, in the same per-file
order — so the two blocks can be zipped positionally. The `--raw` block is
authoritative for change_type + old_path (unambiguous status letters and
tab-separated path columns); the `--numstat` block is authoritative for
additions/deletions/is_binary. This produces strictly more correct,
unambiguous data than parsing `--numstat`'s arrow notation alone, and the
`file_changes` rows landed still conform exactly to the frozen contract.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import storage
from . import __version__ as GITGRAPH_VERSION

RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"

# Fields for the metadata-only pass (no diff output mixed in, so body
# parsing is unambiguous).
_META_PRETTY_FIELDS = ["%H", "%P", "%aI", "%an", "%ae", "%cI", "%cn", "%ce", "%s", "%b"]
_META_PRETTY_FORMAT = RECORD_SEP + FIELD_SEP.join(_META_PRETTY_FIELDS)

# Fields for the diff-only pass (sha marker only; raw+numstat lines follow).
_DIFF_PRETTY_FORMAT = RECORD_SEP + "%H"

NUMSTAT_RE = re.compile(r"^(?P<add>\d+|-)\t(?P<del>\d+|-)\t(?P<path>.*)$")
RAW_RE = re.compile(r"^:\d+ \d+ \S+ \S+ (?P<status>[A-Za-z])\d*\t(?P<rest>.*)$")

_RAW_STATUS_TO_CHANGE_TYPE = {
    "A": "add",
    "M": "modify",
    "D": "delete",
    "R": "rename",
    "C": "copy",
    "T": "modify",  # typechange (e.g. file <-> symlink) — no dedicated type in v1
}


class GitError(RuntimeError):
    """Raised when a `git` subprocess invocation fails or returns
    output this extractor doesn't know how to parse."""


def _run_git(repo_path: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result


@dataclass
class CommitRecord:
    sha: str
    parents: list[str]
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    authored_at: str
    committed_at: str
    subject: str
    body: str


def parse_numstat_line(line: str) -> dict:
    """Parse a single `--numstat` line into additions/deletions/is_binary/
    path/old_path.

    Handles the three cases that matter:
      - binary:  "-\t-\t<path>"                       -> is_binary, no counts
      - rename:  "<add>\t<del>\t<old> => <new>" (or with brace-factored
                 common prefix/suffix, e.g. "dir/{old => new}/f.txt")
      - normal:  "<add>\t<del>\t<path>"                -> plain add/delete counts
    """
    m = NUMSTAT_RE.match(line)
    if not m:
        raise GitError(f"unparseable numstat line: {line!r}")
    add_s, del_s, path_field = m.group("add"), m.group("del"), m.group("path")
    is_binary = add_s == "-" and del_s == "-"
    additions = None if is_binary else int(add_s)
    deletions = None if is_binary else int(del_s)
    old_path, path = _split_rename_arrow(path_field)
    return {
        "additions": additions,
        "deletions": deletions,
        "is_binary": is_binary,
        "path": path,
        "old_path": old_path,
    }


def _split_rename_arrow(path_field: str) -> tuple[str | None, str]:
    """Split git's numstat rename notation into (old_path, new_path).

    Handles both `old/path.txt => new/path.txt` and the brace-factored
    form `common/{old => new}/suffix.txt`. Returns (None, path_field) when
    there's no arrow (plain add/delete/modify).
    """
    brace_m = re.match(r"^(?P<pre>[^{]*)\{(?P<old>[^}]*) => (?P<new>[^}]*)\}(?P<post>.*)$", path_field)
    if brace_m:
        pre, old, new, post = brace_m.group("pre", "old", "new", "post")
        return f"{pre}{old}{post}", f"{pre}{new}{post}"
    if " => " in path_field:
        old, new = path_field.split(" => ", 1)
        return old, new
    return None, path_field


def parse_raw_line(line: str) -> dict:
    """Parse a single `--raw` diff line into change_type/old_path/path.

    Raw lines look like:
      :100644 100644 <old-sha> <new-sha> M\t<path>
      :100644 100644 <old-sha> <new-sha> R064\t<old-path>\t<new-path>
    The status letter (before any similarity-score digits) is authoritative
    for change_type; renames/copies carry two tab-separated paths.
    """
    m = RAW_RE.match(line)
    if not m:
        raise GitError(f"unparseable raw diff line: {line!r}")
    status = m.group("status").upper()
    rest = m.group("rest")
    parts = rest.split("\t")
    change_type = _RAW_STATUS_TO_CHANGE_TYPE.get(status)
    if change_type is None:
        raise GitError(f"unrecognized raw diff status {status!r} in line: {line!r}")
    if len(parts) >= 2:
        old_path, path = parts[0], parts[1]
    else:
        old_path, path = None, parts[0]
    if change_type not in ("rename", "copy"):
        old_path = None
    return {"change_type": change_type, "old_path": old_path, "path": path}


def build_file_changes(raw_lines: list[str], numstat_lines: list[str]) -> list[dict]:
    """Zip a commit's `--raw` lines with its `--numstat` lines (git emits
    them in matching per-file order) into file_changes rows."""
    if len(raw_lines) != len(numstat_lines):
        raise GitError(
            f"raw/numstat line count mismatch ({len(raw_lines)} vs {len(numstat_lines)})"
        )
    changes = []
    for raw_line, num_line in zip(raw_lines, numstat_lines):
        raw = parse_raw_line(raw_line)
        num = parse_numstat_line(num_line)
        changes.append(
            {
                "file_path": raw["path"],
                "additions": num["additions"],
                "deletions": num["deletions"],
                "is_binary": 1 if num["is_binary"] else 0,
                "change_type": raw["change_type"],
                "old_path": raw["old_path"],
            }
        )
    return changes


def extract_commits_meta(repo_path: Path) -> list[CommitRecord]:
    out = _run_git(
        repo_path,
        ["log", "--all", "--date-order", f"--pretty=format:{_META_PRETTY_FORMAT}"],
    ).stdout
    commits: list[CommitRecord] = []
    for chunk in out.split(RECORD_SEP):
        if not chunk:
            continue
        fields = chunk.split(FIELD_SEP)
        if len(fields) < 10:
            raise GitError(f"malformed commit metadata record: {chunk!r}")
        (
            sha,
            parents_raw,
            authored_at,
            author_name,
            author_email,
            committed_at,
            committer_name,
            committer_email,
            subject,
        ) = fields[:9]
        body = FIELD_SEP.join(fields[9:])
        if body.endswith("\n"):
            body = body[:-1]
        parents = parents_raw.split() if parents_raw.strip() else []
        commits.append(
            CommitRecord(
                sha=sha,
                parents=parents,
                author_name=author_name,
                author_email=author_email,
                committer_name=committer_name,
                committer_email=committer_email,
                authored_at=authored_at,
                committed_at=committed_at,
                subject=subject,
                body=body,
            )
        )
    return commits


def extract_file_changes(repo_path: Path) -> dict[str, list[dict]]:
    out = _run_git(
        repo_path,
        ["log", "--all", "--date-order", "--numstat", "--raw", "-M", "-C", f"--pretty=format:{_DIFF_PRETTY_FORMAT}"],
    ).stdout
    changes_by_sha: dict[str, list[dict]] = {}
    for chunk in out.split(RECORD_SEP):
        if not chunk:
            continue
        lines = chunk.split("\n")
        sha = lines[0]
        raw_lines, numstat_lines = [], []
        for line in lines[1:]:
            if not line:
                continue
            if line.startswith(":"):
                raw_lines.append(line)
            elif NUMSTAT_RE.match(line):
                numstat_lines.append(line)
        changes_by_sha[sha] = build_file_changes(raw_lines, numstat_lines)
    return changes_by_sha


def extract_refs(repo_path: Path) -> list[dict]:
    result = _run_git(repo_path, ["show-ref", "--dereference"], check=False)
    if result.returncode != 0:
        # `git show-ref` exits 1 (no stderr) when the repo has no refs at
        # all (e.g. a brand-new repo with no commits yet).
        if result.stdout.strip() == "" and result.returncode == 1:
            return []
        raise GitError(f"git show-ref failed (exit {result.returncode}): {result.stderr.strip()}")

    heads: dict[str, str] = {}
    tags: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, ref = line.split(" ", 1)
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/"):]] = sha
        elif ref.startswith("refs/tags/"):
            if ref.endswith("^{}"):
                name = ref[len("refs/tags/"):-len("^{}")]
                tags[name] = sha  # peeled (dereferenced) commit sha wins
            else:
                name = ref[len("refs/tags/"):]
                tags.setdefault(name, sha)
    refs = [{"name": n, "type": "branch", "target_sha": s} for n, s in heads.items()]
    refs += [{"name": n, "type": "tag", "target_sha": s} for n, s in tags.items()]
    return refs


def get_head_sha(repo_path: Path) -> str:
    return _run_git(repo_path, ["rev-parse", "HEAD"]).stdout.strip()


def analyze(
    repo_path: str | Path,
    db_path: str | Path,
    *,
    display_identity: str | None = None,
) -> int:
    """Run a full extraction of `repo_path` into the commit-store SQLite
    file at `db_path`, replacing all commits/commit_parents/refs/
    file_changes rows. Returns the number of commits written.

    `repo_path` is always the local filesystem path git commands are run
    against. `display_identity`, if given, is what gets recorded in
    `meta.repo_path` instead of `repo_path` itself — used by the CLI (per
    ADR 0003) when the original `analyze` target was a URL: the local
    clone-cache path is still what's operated on, but the URL is what's
    stored, so a URL-sourced db stays self-describing. Defaults to
    `str(repo_path.resolve())`, i.e. today's behavior, when not given."""
    repo_path = Path(repo_path).resolve()
    recorded_path = display_identity if display_identity is not None else str(repo_path)
    commits = extract_commits_meta(repo_path)
    file_changes_by_sha = extract_file_changes(repo_path)
    refs = extract_refs(repo_path)
    head_sha = get_head_sha(repo_path)

    conn = storage.open_db(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM file_changes")
            conn.execute("DELETE FROM commit_parents")
            conn.execute("DELETE FROM refs")
            conn.execute("DELETE FROM commits")

            conn.executemany(
                """
                INSERT INTO commits
                    (sha, author_name, author_email, committer_name, committer_email,
                     authored_at, committed_at, subject, body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.sha,
                        c.author_name,
                        c.author_email,
                        c.committer_name,
                        c.committer_email,
                        c.authored_at,
                        c.committed_at,
                        c.subject,
                        c.body,
                    )
                    for c in commits
                ],
            )

            parent_rows = [
                (c.sha, parent_sha, order)
                for c in commits
                for order, parent_sha in enumerate(c.parents)
            ]
            conn.executemany(
                "INSERT INTO commit_parents (child_sha, parent_sha, parent_order) VALUES (?, ?, ?)",
                parent_rows,
            )

            file_change_rows = [
                (
                    sha,
                    fc["file_path"],
                    fc["additions"],
                    fc["deletions"],
                    fc["is_binary"],
                    fc["change_type"],
                    fc["old_path"],
                )
                for sha, changes in file_changes_by_sha.items()
                for fc in changes
            ]
            conn.executemany(
                """
                INSERT INTO file_changes
                    (commit_sha, file_path, additions, deletions, is_binary, change_type, old_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                file_change_rows,
            )

            conn.executemany(
                "INSERT INTO refs (name, type, target_sha) VALUES (?, ?, ?)",
                [(r["name"], r["type"], r["target_sha"]) for r in refs],
            )

            extracted_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO meta (repo_path, head_sha, extracted_at, gitgraph_version, scc_version)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(repo_path) DO UPDATE SET
                    head_sha = excluded.head_sha,
                    extracted_at = excluded.extracted_at,
                    gitgraph_version = excluded.gitgraph_version,
                    scc_version = excluded.scc_version
                """,
                (recorded_path, head_sha, extracted_at, GITGRAPH_VERSION),
            )
    finally:
        conn.close()

    return len(commits)
