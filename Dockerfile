# GitGraph — modular monolith, one image (ADR 0001/0002: `ghcr.io/seanerama/gitgraph`).
# "Deploy" for this stage means: this image builds and `gitgraph serve` runs
# locally in it — no remote target yet (ADR 0002).
FROM python:3.12-slim

WORKDIR /app

# curl: used for the container's own HEALTHCHECK and by CI to verify the
# server responds (see .github/workflows/ci.yml) — curl'd from *inside* the
# container via `docker exec`, not from the host. See the NOTE below on why.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY gitgraph ./gitgraph

RUN pip install --no-cache-dir .

# Mount point for the commit-store SQLite db produced by `gitgraph analyze`
# on the host (or in another build step) — this image only serves, it
# doesn't run `analyze` itself.
RUN mkdir -p /data
VOLUME ["/data"]
ENV GITGRAPH_DB=/data/gitgraph.db
ENV GITGRAPH_PORT=8000

EXPOSE 8000

# NOTE on networking: `gitgraph serve` binds 127.0.0.1 ONLY, inside its own
# network namespace (ADR 0002 / stage-2 spec — this is a real security
# property, not just style, so it is not relaxed here for container
# convenience). That means standard `docker run -p host:container` port
# publishing will NOT reach it — Docker's NAT forwards to the container's
# external interface, not its loopback. To reach the dashboard from a
# container run this way:
#   - `docker exec <container> curl http://127.0.0.1:8000/api/summary`
#     (same network namespace as the process — this is how CI verifies the
#     container serves real data), or
#   - `docker run --network host ...` (Linux only) to browse from the host.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
    CMD curl -sf http://127.0.0.1:${GITGRAPH_PORT}/api/summary || exit 1

CMD ["sh", "-c", "gitgraph serve --db \"$GITGRAPH_DB\" --port \"$GITGRAPH_PORT\""]
