// Minimal vanilla-JS shell (no build step, no framework — ADR 0001) that
// fetches /api/summary on load and renders the summary stat panel. The
// commit-list rendering that used to live here (a plain <ul>, explicitly a
// placeholder) has been superseded by the interactive D3 commit graph —
// see graph.js, which fetches /api/commits itself and owns the #graph
// panel.

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    let message = resp.statusText;
    try {
      const body = await resp.json();
      if (body && body.error && body.error.message) {
        message = body.error.message;
      }
    } catch (_) {
      // response wasn't JSON; fall back to statusText
    }
    throw new Error(`${url} -> ${resp.status}: ${message}`);
  }
  return resp.json();
}

function renderSummary(summary) {
  document.getElementById("repo-path").textContent = summary.repo_path;

  const stats = [
    ["Commits", summary.commit_count],
    ["Contributors", summary.contributor_count],
    ["First commit", summary.first_commit_at ? summary.first_commit_at.slice(0, 10) : "–"],
    ["Last commit", summary.last_commit_at ? summary.last_commit_at.slice(0, 10) : "–"],
  ];

  const el = document.getElementById("summary");
  el.innerHTML = "";
  for (const [label, value] of stats) {
    const div = document.createElement("div");
    div.className = "stat";

    const valueEl = document.createElement("div");
    valueEl.className = "value";
    valueEl.textContent = value === null || value === undefined ? "–" : value;

    const labelEl = document.createElement("div");
    labelEl.className = "label";
    labelEl.textContent = label;

    div.appendChild(valueEl);
    div.appendChild(labelEl);
    el.appendChild(div);
  }
}

async function main() {
  try {
    const summary = await fetchJSON("/api/summary");
    renderSummary(summary);
  } catch (err) {
    document.getElementById("error").textContent = `Failed to load dashboard data: ${err.message}`;
  }
}

main();
