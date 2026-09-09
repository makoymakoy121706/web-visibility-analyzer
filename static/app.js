const input = document.getElementById("url-input");
const btn = document.getElementById("analyze-btn");
const results = document.getElementById("results");

const GRADE_COLOR = {
  A: "#34d399", B: "#34d399", C: "#f5a742", D: "#fb923c", F: "#f87171",
};
const CAT_COLOR = { SEO: "#2dd4a7", AEO: "#f5a742", GEO: "#a78bfa" };

btn.addEventListener("click", () => runAnalysis());
input.addEventListener("keydown", (e) => { if (e.key === "Enter") runAnalysis(); });
document.querySelectorAll(".examples button").forEach(b => {
  b.addEventListener("click", () => { input.value = b.dataset.url; runAnalysis(); });
});

async function runAnalysis(overrideUrl) {
  const url = (overrideUrl || input.value).trim();
  if (!url) return;
  input.value = url;

  btn.disabled = true;
  results.innerHTML = `
    <div class="status">
      <div class="spinner"></div>
      Fetching the page and scoring SEO, AEO & GEO signals&hellip;
      <div class="sub">GEO scoring calls an LLM — this can take a few seconds.</div>
    </div>`;

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
      ${ring(report.overall_score, GRADE_COLOR[report.overall_grade], 108, 9, "1.7rem")}
      <div class="meta-block">
        <div class="url">${escapeHtml(report.final_url)}</div>
        <div class="sub">Grade <b>${report.overall_grade}</b> &middot; GEO scoring via <b>${escapeHtml(report.llm_provider)}</b></div>
      </div>
    </div>
    <div class="categories">
      ${cats.map(catCard).join("")}
    </div>
    ${cats.map(findingsBlock).join("")}
    <div class="actions">
      <h3>🎯 Top Actions — Do These First</h3>
      <ol>${report.top_actions.map((a, i) => `<li><span class="num">${i + 1}</span><span>${escapeHtml(a)}</span></li>`).join("") || "<li>No high-priority issues found.</li>"}</ol>
    </div>
  `;

  document.querySelectorAll(".cat-card").forEach(card => {
    card.addEventListener("click", () => {
      const target = document.querySelector(`.findings[data-cat="${card.dataset.cat}"]`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
      toggleFindings(card.dataset.cat, true);
    });
  });
  document.querySelectorAll(".findings-header").forEach(h => {
    h.addEventListener("click", () => toggleFindings(h.parentElement.dataset.cat));
  });
  // open the lowest-scoring category by default
  const worst = [...cats].sort((a, b) => a.score - b.score)[0];
  toggleFindings(worst.category, true);
}

function toggleFindings(cat, forceOpen) {
  const body = document.querySelector(`.findings[data-cat="${cat}"] .findings-body`);
  const chev = document.querySelector(`.findings[data-cat="${cat}"] .chev`);
  if (!body) return;
  const shouldOpen = forceOpen || !body.classList.contains("open");
  body.classList.toggle("open", shouldOpen);
  if (chev) chev.textContent = shouldOpen ? "▾" : "▸";
}

function ring(score, color, size, stroke, fontSize) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - score / 100);
  return `
    <div class="ring-wrap" style="width:${size}px;height:${size}px;">
      <svg width="${size}" height="${size}">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="${stroke}" />
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
          stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${offset}"
          style="transition: stroke-dashoffset 0.8s ease-out;" />
      </svg>
      <div class="ring-label">
        <div class="num" style="font-size:${fontSize};color:${color};">${score}</div>
      </div>
    </div>`;
}

function catCard(cat) {
  const color = CAT_COLOR[cat.category];
  const gradeColor = GRADE_COLOR[cat.grade];
  return `
    <div class="cat-card" data-cat="${cat.category}">
      <div class="cat-top">
        <h3>${escapeHtml(cat.category)}</h3>
        <span class="cat-grade" style="background:${gradeColor}22;color:${gradeColor};">${cat.grade}</span>
      </div>
      <div class="cat-score" style="color:${color};">${cat.score}</div>
      <div class="cat-summary">${escapeHtml(cat.summary)}</div>
      <div class="bar"><div class="bar-fill" style="width:${cat.score}%;"></div></div>
      <div class="expand-hint">View findings →</div>
    </div>
  `;
}

function findingsBlock(cat) {
  const failCount = cat.findings.filter(f => !f.passed).length;
  const rows = cat.findings.map(f => `
    <div class="finding ${f.passed ? "pass" : "fail"}">
      <div class="mark">${f.passed ? "✓" : "✕"}</div>
      <div>
        <div class="check">${escapeHtml(f.check)}</div>
        <div class="detail">${escapeHtml(f.detail)}</div>
        ${f.fix ? `<div class="fix">→ ${escapeHtml(f.fix)}</div>` : ""}
      </div>
    </div>
  `).join("");
  return `
    <div class="findings" data-cat="${cat.category}">
      <div class="findings-header">
        <span class="dot"></span>
        <h3>${escapeHtml(cat.category)} Findings</h3>
        <span class="count">${failCount} to fix</span>
        <span class="chev">▸</span>
      </div>
      <div class="findings-body">${rows}</div>
    </div>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
