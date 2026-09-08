# Web Vitals & Search Visibility Analyzer

An AI-powered tool that scores a URL across three visibility surfaces businesses now have to
care about simultaneously:

- **SEO** — will you show up in traditional search results?
- **AEO** — will you get pulled into a featured snippet / direct answer box?
- **GEO** — will ChatGPT, Perplexity, or Gemini cite you when someone asks a generative
  search engine instead of Google?

Every check produces a pass/fail with a specific, actionable fix — not just a score.

## Quick Start

```bash
cd web-visibility-analyzer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional — see "LLM & API Keys" below
```

**CLI:**
```bash
python cli.py analyze https://example.com          # rich terminal report
python cli.py analyze https://example.com --json    # raw JSON, for piping/scripting
```

**Web UI:**
```bash
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

### LLM & API Keys (all optional — the app works with zero keys)

The app runs completely standalone with deterministic heuristic scoring. Add keys to `.env`
to upgrade specific checks to real data:

| Env var | Upgrades | Free tier? |
|---|---|---|
| `GROQ_API_KEY` | GEO qualitative scoring (LLM judges citability) | Yes, generous — [console.groq.com/keys](https://console.groq.com/keys) |
| `GEMINI_API_KEY` | Same, used if Groq isn't set | Yes — Google AI Studio |
| `OPENAI_API_KEY` | Same, used if neither above is set | Pay-as-you-go |
| `PAGESPEED_API_KEY` | Real Core Web Vitals (LCP/CLS/Lighthouse score) instead of a response-time proxy | Yes, no billing required |

Provider selection is automatic priority order (Groq → Gemini → OpenAI → heuristic). If a key
is present but the call fails (rate limit, invalid key, network), the app **falls back to the
heuristic instead of crashing** — every report field says exactly which mode produced it, so a
client-facing report is never silently wrong about its own confidence.

---

## Process Documentation

### Tool selection
- **httpx + BeautifulSoup** for fetching/parsing over Selenium/Playwright — this analyzer
  reads static HTML signals (metadata, schema, headings, text), not rendered JS state. A full
  headless browser is heavier infra for no benefit for the metrics in scope; it's the first
  thing on the roadmap if client-side-rendered sites become a priority (see Roadmap).
- **FastAPI + vanilla JS** over a heavier frontend framework — the deliverable calls for "a
  simple web UI," and a build step / framework here would be pure overhead. FastAPI's
  auto-validation via Pydantic also doubles as the report schema.
- **Groq as default LLM provider** — free tier is fast and generous enough for a demo/small
  client tool, and it's OpenAI-wire-compatible, so the same request code serves Groq and
  OpenAI. Gemini is wired as a second free-tier fallback so the tool doesn't have a single
  point of failure on one vendor's rate limits.
- **rich** for the CLI report — genuinely more legible for demoing to a non-technical
  stakeholder than a wall of print statements, at negligible cost.

### System architecture
```
URL → scraper.py (one fetch, one parse) → PageData
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
                 seo.py                    aeo.py                    geo.py
        (metadata, crawlability,    (schema, Q&A patterns,   (density signals +
         Core Web Vitals proxy)      snippet formatting)      LLM citability judgment)
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              ▼
                                        scoring.py
                                    (weighted findings → 0-100 + grade)
                                              │
                                              ▼
                                   Report (pydantic model)
                                              │
                                   ┌──────────┴──────────┐
                                   ▼                     ▼
                                cli.py               app/main.py
                             (rich / JSON)          (FastAPI + static UI)
```

The site is fetched **once**; all three analyzers read from the same `PageData` object. No
analyzer makes its own network call except `geo.py`'s single LLM call and `seo.py`'s optional
PageSpeed call — keeping the whole run to 1-3 HTTP round trips regardless of how many checks
run.

### Data extraction technique
`scraper.py` does one parse pass and extracts every structural signal the three analyzers
need: title/meta/canonical/viewport/lang, all headings with their tag level, image alt-text
coverage, internal/external link sets, every JSON-LD block (schema.org types), visible text
with scripts/styles stripped, and word count. Downstream analyzers only touch this object —
they never re-parse the DOM — which keeps each category module a pure function of
`PageData → CategoryResult` and easy to unit test in isolation.

### Prompt engineering strategy (GEO)
The qualitative half of GEO — "would an LLM actually cite this?" — is inherently a judgment
call, so it's the one thing delegated to an LLM rather than regex. The prompt in `geo.py`:
- Sets a **strict, evidence-based persona** in the system prompt to counter the default
  helpful/encouraging tone LLMs default to, which would otherwise inflate every score.
- Requests **only JSON matching an explicit schema** (three 0-10 scores + one-sentence
  reasoning + one-sentence improvement each), with `response_format: json_object` /
  `response_mime_type: application/json` set at the API level as a second guardrail.
- Truncates page content to 6,000 characters — enough context to judge tone and structure
  without blowing through free-tier token/rate limits on large pages.
- Parses defensively (`_extract_json` strips markdown fences some models add anyway) and
  raises a typed `LLMUnavailable` on any failure mode, which `geo.py` catches to fall back to
  the heuristic scorer rather than ever surfacing a raw API error to the report.

### Error handling
- `FetchError` for anything network/HTTP-level (bad URL, timeout, 4xx/5xx) — surfaced as a
  422 from the API and a clean stderr message from the CLI, never a stack trace.
- `LLMUnavailable` for any LLM-call failure (missing key, invalid key, rate limit, malformed
  JSON response) — always caught, always falls back to the heuristic scorer. The report
  always states which mode (`heuristic` vs. provider name) produced the GEO section, so
  nothing is silently degraded.
- PageSpeed Insights failures fall back to the response-time/page-weight proxy the same way.

---

## Business Value Justification

Search behavior has fragmented into three channels a business now has to win independently:
a Google results page, a featured-snippet/voice-answer box, and an AI chat answer that may
cite (or skip) them entirely with no click-through at all. Most small-business sites were
built for the first channel only, if that. This tool gives a non-technical client owner:

1. **One number they understand** (0-100, A-F) per channel instead of a vague "your SEO needs
   work."
2. **A ranked action list**, not a data dump — `top_actions` surfaces the highest-weighted
   fixes across all three categories, so a freelancer/agency can hand a client exactly 3-5
   things to fix this week instead of a 40-line audit they'll never act on.
3. **A defensible reason to sell GEO work specifically** — GEO is the newest, least-understood
   of the three, and most competing "SEO audit" tools don't measure it at all. Showing a
   client concretely why ChatGPT wouldn't cite their page (no quotable stats, no entity
   schema, buried answers) is a sales conversation almost no other tool can start yet.
4. **Evidence, not opinion, per finding** — every failed check ships with the specific
   contributing signal (word count, missing tag, LLM's one-sentence reasoning), so
   recommendations survive a skeptical client asking "why."

---

## Product Roadmap

1. **Cross-LLM citation monitoring** — periodically prompt multiple LLMs (ChatGPT, Claude,
   Perplexity, Gemini) with queries relevant to the client's niche and check whether their
   domain actually appears in the response, turning GEO from a readiness score into a
   measured outcome over time.
2. **Competitor benchmarking** — run the same three-category analysis against 2-3 competitor
   URLs alongside the client's, and render a side-by-side comparison so the pitch becomes
   "you're losing to X on GEO specifically" rather than an absolute score in a vacuum.
3. **Automated remediation** — for the mechanical fixes (missing meta description, missing
   Organization/FAQPage schema, missing alt text), generate the actual replacement HTML/JSON-LD
   snippet in the report so implementation is copy-paste rather than another to-do.
4. **Headless-render pass for JS-heavy sites** — add an optional Playwright-based fetch path
   for SPA/client-side-rendered sites, where the current static-HTML fetch would undercount
   content that only exists after hydration.
5. **Historical tracking + scheduled re-scans** — persist reports (SQLite/Postgres) and re-run
   on a schedule, so the product becomes a monitored retainer service ("we re-check your score
   monthly") instead of a one-off report — directly supporting a recurring-revenue offer.
