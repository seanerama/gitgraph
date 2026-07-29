"""`gitgraph` command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import extractor


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

    return parser


def default_db_path(repo_path: Path) -> Path:
    return Path(".gitgraph") / f"{repo_path.name}.db"


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

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
