// Minimal vanilla-JS shell (no build step, no framework — ADR 0001) that
// fetches /api/summary and /api/commits on load and renders the summary
// numbers plus a plain <ul> of recent commits. This is explicitly NOT the
// D3 commit graph — that's a separate later stage; this just proves the
// browser round-trip against the real dashboard-api.

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

function renderCommits(nodes) {
  const list = document.getElementById("commits");
  list.innerHTML = "";
  const recent = nodes.slice(0, 20);
  if (recent.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No commits found.";
    list.appendChild(li);
    return;
  }
  for (const node of recent) {
    const li = document.createElement("li");

    const sha = document.createElement("code");
    sha.textContent = node.sha.slice(0, 7);

    li.appendChild(sha);
    li.appendChild(document.createTextNode(` ${node.subject} — ${node.author_name}`));
    list.appendChild(li);
  }
}

async function main() {
  try {
    const [summary, commits] = await Promise.all([
      fetchJSON("/api/summary"),
      fetchJSON("/api/commits"),
    ]);
    renderSummary(summary);
    renderCommits(commits.nodes);
  } catch (err) {
    document.getElementById("error").textContent = `Failed to load dashboard data: ${err.message}`;
  }
}

main();
