"""`gitgraph` command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import extractor

# ADR 0002 (defer remote deployment target): gitgraph serve is local-only,
# no auth. Bind is hardcoded to loopback and is NOT exposed as a CLI flag —
# there is deliberately no way to ask this command to listen on 0.0.0.0.
SERVE_HOST = "127.0.0.1"
SERVE_DEFAULT_PORT = 8000

# `serve` has no repo_path argument to derive a per-repo default from (unlike
# `analyze`), so it falls back to a fixed path under .gitgraph/ relative to
# cwd. Override with --db to point at a specific analyzed repo's db.
DEFAULT_DB_PATH = Path(".gitgraph") / "gitgraph.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gitgraph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze", help="Extract commit history from a git repo into a commit-store SQLite db"
    )
    analyze_parser.add_argument("repo_path", help="Path to the git repository to analyze")
    analyze_parser.add_argument(
        "--db",
        default=None,
        help="Path to the SQLite db to write (default: .gitgraph/<repo-name>.db)",
    )

    serve_parser = subparsers.add_parser(
        "serve", help="Serve the dashboard API and static shell for an analyzed repo"
    )
    serve_parser.add_argument(
        "--db",
        default=None,
        help=f"Path to the commit-store SQLite db to read (default: {DEFAULT_DB_PATH})",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=SERVE_DEFAULT_PORT,
        help=f"Port to bind on 127.0.0.1 (default: {SERVE_DEFAULT_PORT})",
    )

    return parser


def default_db_path(repo_path: Path) -> Path:
    return Path(".gitgraph") / f"{repo_path.name}.db"


def build_uvicorn_config(db_path: str | Path, port: int):
    """Build (but do not run) the uvicorn Config `gitgraph serve` uses.

    Split out from `run_server` so tests can assert the bind host/port
    without actually starting a server. Always binds `SERVE_HOST`
    (127.0.0.1) — never configurable to 0.0.0.0 — per ADR 0002.
    """
    import uvicorn

    from .api import create_app

    app = create_app(db_path)
    return uvicorn.Config(app, host=SERVE_HOST, port=port, log_level="info")


def run_server(db_path: str | Path, port: int) -> None:
    import uvicorn

    config = build_uvicorn_config(db_path, port)
    uvicorn.Server(config).run()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        repo_path = Path(args.repo_path).resolve()
        if not (repo_path / ".git").exists() and not (repo_path / "HEAD").exists():
            print(f"gitgraph: {repo_path} does not look like a git repository", file=sys.stderr)
            return 1
        db_path = Path(args.db) if args.db else default_db_path(repo_path)
        try:
            count = extractor.analyze(repo_path, db_path)
        except extractor.GitError as exc:
            print(f"gitgraph: {exc}", file=sys.stderr)
            return 1
        print(f"gitgraph: wrote {count} commits from {repo_path} to {db_path}")
        return 0

    if args.command == "serve":
        db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
        if not db_path.exists():
            print(
                f"gitgraph: no commit-store db found at {db_path} — "
                f"run `gitgraph analyze <repo-path> --db {db_path}` first",
                file=sys.stderr,
            )
            return 1
        print(f"gitgraph: serving {db_path} on http://{SERVE_HOST}:{args.port}/")
        run_server(db_path, args.port)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
