# 0002. Defer remote deployment target for GitGraph

- **Status:** Accepted
- **Date:** 2026-07-29

## Context

The Architect stage normally picks a deployment target from the operator's
global catalog (`verity deployment list`) so `/verity:ship` has somewhere to
build `deploy.sh` against. GitGraph's own catalog offers `coolify` (PaaS on
the EC2 box, explicitly described as "where built apps get promoted"),
`ec2-primary` (direct SSH/docker-compose), `cloudflare-pages` (static only —
doesn't fit, GitGraph has a real backend), and `eas-github-releases`
(mobile — not applicable).

GitGraph is, at its core, a CLI + local dashboard tool: `gitgraph analyze
<repo-path>` followed by `gitgraph serve` against a local SQLite file. Nothing
in the walking skeleton or the near-term feature set requires it to be
reachable over the public internet — it operates on whatever repo the
operator points it at, which for a hosted instance would itself be an
access/security question (whose repos? public only, or private with
credentials?) not yet decided.

## Decision

Do not pick a remote deployment target during this Architect pass. GitGraph
ships and is verified as a **local** service for now: `gitgraph serve` bound
to localhost, run via a container image (`ghcr.io/seanerama/gitgraph`) or
directly via the Python package. The walking skeleton's "deployed" criterion
is satisfied by **"container builds and runs locally, `gitgraph serve` reachable
on localhost"** rather than a remote host being green.

`.verity/deploy-access.md` is left unwritten. `/verity:ship` will need a real
target before it can promote GitGraph past local — at that point, re-run this
decision (most likely landing on `coolify`, given it's the stated home for
promoted apps and already runs on infrastructure the operator controls).

## Alternatives considered

- **Coolify PaaS** — best structural fit (container → GitHub-driven build →
  domain), but promoting a repo-analytics tool to a public domain raises an
  unresolved question (does it analyze the operator's own repos only, or take
  arbitrary repo URLs from visitors — a very different security posture) that
  shouldn't be decided as a side effect of an infra choice. Revisit once
  GitGraph's multi-repo/hosted story is actually designed.
- **EC2 direct (docker-compose)** — same objection as Coolify, plus more
  manual ops for no offsetting benefit at this stage.
- **Picking a target now "to be safe"** — rejected; the guide's walking-skeleton
  goal is to prove the real deploy environment, and picking one prematurely
  just to have an ADR would prove nothing real and would need revisiting anyway.

## Consequences

- `/verity:ship` cannot promote GitGraph to a remote host until this ADR is
  revisited and a target is chosen — that's a deliberate, explicit gap, not an
  oversight.
- The walking skeleton's CI must still prove build + run + one real test green,
  just without a remote deploy step; `deploy.sh` targets "run the container
  locally" for now.
- When a remote target is chosen later, the access-story question (whose repos
  does a hosted GitGraph analyze) must be answered in the same pass — it's a
  security decision, not just an infra one.
