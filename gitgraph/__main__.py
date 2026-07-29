"""Allows `python -m gitgraph analyze <repo-path>` in addition to the
installed `gitgraph` console script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
