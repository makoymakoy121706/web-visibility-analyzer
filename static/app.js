const input = document.getElementById("url-input");
const btn = document.getElementById("analyze-btn");
const results = document.getElementById("results");

btn.addEventListener("click", runAnalysis);
input.addEventListener("keydown", (e) => { if (e.key === "Enter") runAnalysis(); });

async function runAnalysis() {
  const url = input.value.trim();
  if (!url) return;

  btn.disabled = true;
  results.innerHTML = `<div class="status">Fetching page, running SEO/AEO checks, and asking the LLM to judge GEO citability… this can take a few seconds.</div>`;

  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Analysis failed");
    render(data);
  } catch (err) {
    results.innerHTML = `<div class="error">${escapeHtml(err.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function render(report) {
  const cats = [report.seo, report.aeo, report.geo];
  results.innerHTML = `
    <div class="overall">
      <div class="score grade-${report.overall_grade}">${report.overall_score}/100 &middot; ${report.overall_grade}</div>
      <div class="meta">${escapeHtml(report.final_url)} &middot; GEO scoring via ${escapeHtml(report.llm_provider)}</div>
    </div>
    <div class="categories">
      ${cats.map(catCard).join("")}
    </div>
    ${cats.map(findingsBlock).join("")}
    <div class="actions">
      <h3>Top Actions — Do These First</h3>
      <ol>${report.top_actions.map(a => `<li>${escapeHtml(a)}</li>`).join("") || "<li>No high-priority issues found.</li>"}</ol>
    </div>
  `;
}

function catCard(cat) {
  return `
    <div class="cat-card">
      <h3>${escapeHtml(cat.category)}</h3>
      <div class="cat-score grade-${cat.grade}">${cat.score}/100</div>
      <div class="cat-summary">${escapeHtml(cat.summary)}</div>
    </div>
  `;
}

function findingsBlock(cat) {
  const rows = cat.findings.map(f => `
    <div class="finding ${f.passed ? "pass" : "fail"}">
      <div class="mark">${f.passed ? "✓" : "✗"}</div>
      <div>
        <div class="check">${escapeHtml(f.check)}</div>
        <div class="detail">${escapeHtml(f.detail)}</div>
        ${f.fix ? `<div class="fix">→ ${escapeHtml(f.fix)}</div>` : ""}
      </div>
    </div>
  `).join("");
  return `<div class="findings"><h3>${escapeHtml(cat.category)} Findings</h3>${rows}</div>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
