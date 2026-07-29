# Assessment: initial thin backlog — walking skeleton

- **Date:** 2026-07-29
- **Request:** Mode A batch decomposition — turn the Architect's design
  (ADR 0001 stack/topology, ADR 0002 deferred deployment, `commit-store` and
  `dashboard-api` contracts) into the initial stage backlog.
- **Decision:** ACCEPT as 2 stages (1, 2), dependency-ordered, forming the
  complete walking skeleton. No further feature stages planned this batch —
  everything past the skeleton (LOC snapshots, churn endpoint, the real D3
  commit-graph UI, contributor metrics) is deliberately deferred until Stages
  1–2 are green in CI, per the guide's "prove the spine before feature work"
  rule.
- **Refs:** ADR 0001, ADR 0002 (`docs/adr/`); `contracts/commit-store.md`,
  `contracts/dashboard-api.md`.

## Verification against the live codebase

| Claim (from ADRs/contracts) | Reality (verified 2026-07-29, gitgraph @ main) | Consequence |
|---|---|---|
| Python/FastAPI/SQLite stack chosen, no code yet | Confirmed — repo contains only scaffold files, ADRs, contracts, and `idea.md`; no `gitgraph/` package exists | Greenfield; Stage 1 originates the package from scratch |
| `ci.yml` comment says "Lint and test gates are added when the Architect chooses the stack and the walking skeleton lands" | Confirmed — current workflow is hygiene-only (structure check + gitleaks), exactly as documented | Stage 1 and Stage 2 each extend `ci.yml` with a real test gate, matching the plan already written into the scaffold |
| `commit-store` v1 defines `snapshots` table for `scc` LOC data | Confirmed in `contracts/commit-store.md` | Deliberately left unpopulated by Stages 1–2 (analyzer/`scc` integration is future work); contract allows a partial-population state since `snapshots` has no NOT NULL cross-table requirement forcing it |
| `dashboard-api` v1 defines 4 endpoints (summary, commits, metrics/loc, metrics/churn) | Confirmed in `contracts/dashboard-api.md` | Stage 2 implements only `/api/summary` and `/api/commits` — contract shape is frozen, not the implementation timeline; the other two ship as later, additive-to-the-backlog stages once the skeleton is green |
| ADR 0002: no remote deploy target, "deploys" = container builds and runs locally | Confirmed, ADR accepted 2026-07-29 | Stage 2's Dockerfile + local `docker run` + curl is the walking skeleton's "deploy" bar, not a real deploy.sh/`/verity:ship` target |

## Contract safety

Both frozen contracts (`commit-store`, `dashboard-api`) originate in this
batch — nothing pre-existing to threaten. Stage 1 originates `commit-store`
exactly as specified (no deviation). Stage 2 consumes it read-only and
implements a strict subset of `dashboard-api` — partial implementation of a
frozen contract's endpoint set is not a contract violation; shipping an
endpoint with a different shape than specified would be.

## Stage map

1. **Extract commit history into commit-store SQLite** (feature, no deps) —
   `gitgraph analyze <repo-path>`: git log/numstat/refs → SQLite per
   `commit-store` v1. First real (non-hygiene) CI gate.
2. **Serve dashboard API and minimal shell** (feature, depends on 1) —
   `gitgraph serve`: FastAPI `/api/summary` + `/api/commits` per
   `dashboard-api` v1, plus a bare static page proving the browser round-trip.
   Dockerfile added; CI builds + runs the container and curls it. Completes
   the walking skeleton.

Stages 1 and 2 are sequential (2 needs 1's SQLite output to query) — not
parallelizable.

## Deliberately deferred

- `scc`/`snapshots` analyzer and `/api/metrics/loc` — needs the skeleton
  proven first; also needs a sampling-policy decision (every commit vs.
  daily/weekly vs. tags-only per `idea.md`) that's product judgment, not
  pure plumbing — better made once real repo data is visible.
- `/api/metrics/churn` — cheap to add (pure derive from `file_changes` +
  `commits`, no new dependency) but withheld from Stage 2 to keep that stage
  small and focused on proving the serve path; natural next stage after the
  skeleton is green.
- The real D3 commit-graph + synced-panel frontend (`idea.md`'s actual
  vision) — Stage 2's shell is a deliberately thin proof, not the product;
  planned as its own stage(s) once data endpoints exist to visualize.
- Contributors/hotspots/ownership metrics, GitHub PR/issue/CI enrichment —
  all explicitly named in `idea.md` as later, GitHub-API-dependent work; not
  planned this batch.
- Remote deployment (Coolify) — blocked on ADR 0002 being revisited with a
  hosted-access-model decision.
- In-app help agent (`helper-bot` catalog feature) — declined by the
  operator during the Architect pass (no chat/LLM loop in this app).

## Outcome

Pending — Stages 1 and 2 handed to `/verity:build`.
