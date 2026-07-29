// Interactive D3 commit-graph panel (Stage 4). Renders `/api/commits`'s
// `nodes` (sha, parents, author_name, author_email, authored_at, subject,
// refs) as a zoomable/pannable SVG DAG: X-axis is commit time, Y-axis is a
// simple "lane" heuristic that keeps parallel branches visually distinct.
//
// This is intentionally separate from app.js (which only renders the
// summary stat panel now — its old renderCommits()/<ul> responsibility is
// superseded entirely by this file).
//
// Tooltip note: idea.md's original tooltip wishlist also mentions a
// files-changed count. That data is NOT available from `/api/commits` in
// the frozen v1 dashboard-api contract (no numstat rollup on this
// endpoint), and adding it would require a new endpoint / contract change,
// which is explicitly out of scope for this stage. It is omitted from the
// tooltip below; see stage-instructions/stage-4-ui-smoke.md for the same
// note.

const MAX_RENDERED_COMMITS = 300;

const LANE_HEIGHT = 40;
const NODE_RADIUS = 5;
const MARGIN = { top: 30, right: 40, bottom: 30, left: 40 };
const MIN_PLOT_WIDTH = 800;
const COMMIT_SPACING = 24; // px per commit, minimum, before zoom

/** Assign each commit a "lane" (an integer track) using a simple
 * chronological heuristic:
 *  - a root commit (no parents in the rendered set) gets the first free lane.
 *  - a commit with one rendered parent inherits that parent's lane if it's
 *    the parent's first-listed (chronologically first) child AND that lane
 *    hasn't already been claimed by an earlier sibling; otherwise it's a
 *    fork and gets a new lane.
 *  - a merge commit (2+ rendered parents) inherits its first parent's lane
 *    the same way, and frees up its other parent lane(s) for reuse (the
 *    branch being merged in is treated as ending at the merge).
 *
 * This does not need to be crossing-minimal/optimal per the stage spec —
 * just enough to make parallel branches visually distinguishable. */
function assignLanes(nodesAsc) {
  const laneOfSha = new Map();
  const laneTip = []; // laneTip[lane] = sha currently occupying that lane, or null if free

  const childrenOf = new Map(); // parentSha -> [childSha, ...] in chronological order
  for (const n of nodesAsc) {
    for (const p of n.parents) {
      if (!childrenOf.has(p)) childrenOf.set(p, []);
      childrenOf.get(p).push(n.sha);
    }
  }

  function firstFreeLane() {
    for (let i = 0; i < laneTip.length; i++) {
      if (laneTip[i] === null) return i;
    }
    laneTip.push(null);
    return laneTip.length - 1;
  }

  for (const n of nodesAsc) {
    const parentsInSet = n.parents.filter((p) => laneOfSha.has(p));
    let lane;

    if (parentsInSet.length === 0) {
      lane = firstFreeLane();
    } else {
      const primaryParent = parentsInSet[0];
      const parentLane = laneOfSha.get(primaryParent);
      const isFirstChild = childrenOf.get(primaryParent)[0] === n.sha;
      if (isFirstChild && laneTip[parentLane] === primaryParent) {
        lane = parentLane;
      } else {
        lane = firstFreeLane();
      }

      // Merge commit: reconcile other parent lane(s) by freeing them for
      // reuse now that branch has merged in.
      for (let i = 1; i < parentsInSet.length; i++) {
        const otherLane = laneOfSha.get(parentsInSet[i]);
        if (laneTip[otherLane] === parentsInSet[i]) {
          laneTip[otherLane] = null;
        }
      }
    }

    laneOfSha.set(n.sha, lane);
    laneTip[lane] = n.sha;
  }

  const laneCount = laneTip.length;
  return { laneOfSha, laneCount };
}

function shortSha(sha) {
  return sha ? sha.slice(0, 7) : "";
}

function formatDate(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function buildTooltipHTML(node) {
  const refs = node.refs && node.refs.length ? node.refs.join(", ") : "(none)";
  const parents = node.parents && node.parents.length
    ? node.parents.map(shortSha).join(", ")
    : "(root commit)";
  const subject = node.subject || "(no subject)";
  return (
    `<div class="tooltip-subject">${escapeHTML(subject)}</div>` +
    `<div><strong>Author:</strong> ${escapeHTML(node.author_name || "")}</div>` +
    `<div><strong>Date:</strong> ${escapeHTML(formatDate(node.authored_at))}</div>` +
    `<div><strong>Refs:</strong> ${escapeHTML(refs)}</div>` +
    `<div><strong>Parents:</strong> ${escapeHTML(parents)}</div>`
  );
}

function escapeHTML(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderTruncationNote(container, shownCount, totalCount) {
  const note = document.getElementById("graph-note");
  if (!note) return;
  if (totalCount > shownCount) {
    note.textContent = `showing ${shownCount} of ${totalCount} commits`;
    note.hidden = false;
  } else {
    note.textContent = "";
    note.hidden = true;
  }
}

function renderGraph(nodes) {
  const container = document.getElementById("graph");
  container.innerHTML = "";

  if (!nodes || nodes.length === 0) {
    const empty = document.createElement("p");
    empty.className = "note";
    empty.textContent = "No commits to display.";
    container.appendChild(empty);
    renderTruncationNote(container, 0, 0);
    return;
  }

  const totalCount = nodes.length;

  // API returns nodes ordered by authored_at DESC. Take the most recent
  // MAX_RENDERED_COMMITS, then sort ascending (oldest -> newest, left ->
  // right) for rendering.
  const capped = nodes.slice(0, MAX_RENDERED_COMMITS);
  const nodesAsc = capped
    .slice()
    .sort((a, b) => new Date(a.authored_at) - new Date(b.authored_at));

  renderTruncationNote(container, nodesAsc.length, totalCount);

  const { laneOfSha, laneCount } = assignLanes(nodesAsc);

  const plotWidth = Math.max(MIN_PLOT_WIDTH, nodesAsc.length * COMMIT_SPACING);
  const width = plotWidth + MARGIN.left + MARGIN.right;
  const height = Math.max(1, laneCount) * LANE_HEIGHT + MARGIN.top + MARGIN.bottom;

  const svg = d3
    .select(container)
    .append("svg")
    .attr("width", "100%")
    .attr("height", Math.min(height, 480))
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMinYMin meet");

  const root = svg.append("g").attr("class", "graph-root");

  const x = d3
    .scaleTime()
    .domain(d3.extent(nodesAsc, (d) => new Date(d.authored_at)))
    .range([MARGIN.left, width - MARGIN.right]);

  const y = (lane) => MARGIN.top + lane * LANE_HEIGHT + LANE_HEIGHT / 2;

  const nodeBySha = new Map(nodesAsc.map((n) => [n.sha, n]));

  // Edges: one per (commit, parent) pair where the parent is also rendered.
  // Merge commits (2+ rendered parents) get a distinct style for edges
  // beyond the first parent.
  const edges = [];
  for (const n of nodesAsc) {
    const parentsInSet = n.parents.filter((p) => nodeBySha.has(p));
    parentsInSet.forEach((p, i) => {
      edges.push({
        source: n,
        target: nodeBySha.get(p),
        isMerge: parentsInSet.length > 1,
        isPrimary: i === 0,
      });
    });
  }

  const linkGen = d3
    .linkHorizontal()
    .x((d) => d.x)
    .y((d) => d.y);

  root
    .append("g")
    .attr("class", "edges")
    .selectAll("path")
    .data(edges)
    .join("path")
    .attr("class", (d) => (d.isMerge && !d.isPrimary ? "edge edge-merge" : "edge edge-normal"))
    .attr("d", (d) =>
      linkGen({
        source: { x: x(new Date(d.source.authored_at)), y: y(laneOfSha.get(d.source.sha)) },
        target: { x: x(new Date(d.target.authored_at)), y: y(laneOfSha.get(d.target.sha)) },
      })
    );

  const tooltip = document.getElementById("tooltip");

  const nodeSel = root
    .append("g")
    .attr("class", "nodes")
    .selectAll("circle")
    .data(nodesAsc)
    .join("circle")
    .attr("class", "commit-node")
    .attr("r", NODE_RADIUS)
    .attr("cx", (d) => x(new Date(d.authored_at)))
    .attr("cy", (d) => y(laneOfSha.get(d.sha)))
    .on("mouseenter", function (event, d) {
      d3.select(this).classed("commit-node-hover", true);
      if (!tooltip) return;
      tooltip.innerHTML = buildTooltipHTML(d);
      tooltip.hidden = false;
      positionTooltip(tooltip, event);
    })
    .on("mousemove", function (event) {
      if (!tooltip) return;
      positionTooltip(tooltip, event);
    })
    .on("mouseleave", function () {
      d3.select(this).classed("commit-node-hover", false);
      if (!tooltip) return;
      tooltip.hidden = true;
    });

  nodeSel.append("title").text((d) => `${shortSha(d.sha)} ${d.subject || ""}`);

  // Zoom + pan (hard requirement, not polish) — applied to the whole SVG,
  // transforming the root <g> that holds both edges and nodes.
  const zoom = d3
    .zoom()
    .scaleExtent([0.2, 8])
    .on("zoom", (event) => {
      root.attr("transform", event.transform);
    });

  svg.call(zoom);
}

function positionTooltip(tooltip, event) {
  const offset = 12;
  tooltip.style.left = `${event.clientX + offset}px`;
  tooltip.style.top = `${event.clientY + offset}px`;
}

async function loadGraph() {
  try {
    const resp = await fetch("/api/commits");
    if (!resp.ok) {
      throw new Error(`/api/commits -> ${resp.status}`);
    }
    const body = await resp.json();
    renderGraph(body.nodes);
  } catch (err) {
    const container = document.getElementById("graph");
    if (container) {
      const p = document.createElement("p");
      p.id = "error";
      p.textContent = `Failed to load commit graph: ${err.message}`;
      container.appendChild(p);
    }
  }
}

loadGraph();
