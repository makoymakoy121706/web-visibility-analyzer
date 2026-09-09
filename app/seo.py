"""SEO: traditional search-engine readiness -- metadata, crawlability, page structure,
and a Core Web Vitals proxy (real PSI data if PAGESPEED_API_KEY is set, otherwise a
response-time/page-weight heuristic).
"""
from __future__ import annotations

import os

import httpx

from app.models import Finding
from app.scoring import build_category_result, shorten
from app.scraper import PageData

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def analyze_seo(page: PageData):
    findings: list[Finding] = []

    title_len = len(page.title)
    findings.append(Finding(
        check="Title tag present and well-sized",
        passed=bool(page.title) and 15 <= title_len <= 60,
        weight=10,
        detail=f"Title ({title_len} chars): {page.title or '(missing)'}",
        fix="Add a <title> tag between 15-60 characters that includes the primary keyword." if not (page.title and 15 <= title_len <= 60) else None,
    ))

    desc_len = len(page.meta_description)
    findings.append(Finding(
        check="Meta description present and well-sized",
        passed=bool(page.meta_description) and 50 <= desc_len <= 160,
        weight=8,
        detail=f"Meta description ({desc_len} chars): {page.meta_description or '(missing)'}",
        fix="Add a meta description between 50-160 characters that summarizes the page and includes a call to action." if not (page.meta_description and 50 <= desc_len <= 160) else None,
    ))

    h1_preview = [shorten(h) for h in page.h1s[:5]]
    findings.append(Finding(
        check="Exactly one H1 heading",
        passed=len(page.h1s) == 1,
        weight=8,
        detail=f"Found {len(page.h1s)} H1 tag(s): {h1_preview}",
        fix="Use exactly one H1 per page that states the page's main topic." if len(page.h1s) != 1 else None,
    ))

    findings.append(Finding(
        check="Canonical tag present",
        passed=bool(page.canonical),
        weight=6,
        detail=f"Canonical: {page.canonical or '(missing)'}",
        fix="Add a <link rel=\"canonical\"> tag to prevent duplicate-content dilution." if not page.canonical else None,
    ))

    findings.append(Finding(
        check="Mobile viewport configured",
        passed=bool(page.viewport and "width=device-width" in page.viewport),
        weight=8,
        detail=f"Viewport: {page.viewport or '(missing)'}",
        fix="Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">." if not (page.viewport and "width=device-width" in page.viewport) else None,
    ))

    findings.append(Finding(
        check="Served over HTTPS",
        passed=page.is_https,
        weight=8,
        detail="HTTPS" if page.is_https else "HTTP (not secure)",
        fix="Serve the site over HTTPS -- it's both a ranking factor and a trust signal." if not page.is_https else None,
    ))

    findings.append(Finding(
        check="HTML lang attribute set",
        passed=bool(page.lang),
        weight=3,
        detail=f"lang={page.lang or '(missing)'}",
        fix="Add a lang attribute to <html> (e.g. lang=\"en\") for accessibility and locale targeting." if not page.lang else None,
    ))

    alt_total = len(page.images)
    alt_missing = sum(1 for img in page.images if not img.get("alt"))
    alt_ok = alt_total == 0 or alt_missing / alt_total <= 0.1
    findings.append(Finding(
        check="Images have alt text",
        passed=alt_ok,
        weight=6,
        detail=f"{alt_missing}/{alt_total} images missing alt text",
        fix=f"Add descriptive alt text to the {alt_missing} image(s) missing it." if not alt_ok else None,
    ))

    findings.append(Finding(
        check="robots.txt present",
        passed=page.robots_txt_found,
        weight=5,
        detail="Found" if page.robots_txt_found else "Not found",
        fix="Add a robots.txt at the site root to control crawler access explicitly." if not page.robots_txt_found else None,
    ))

    findings.append(Finding(
        check="XML sitemap present",
        passed=page.sitemap_found,
        weight=6,
        detail="Found" if page.sitemap_found else "Not found",
        fix="Publish an XML sitemap and reference it in robots.txt to speed up indexing." if not page.sitemap_found else None,
    ))

    findings.append(Finding(
        check="Sufficient body content",
        passed=page.word_count >= 300,
        weight=6,
        detail=f"{page.word_count} visible words",
        fix="Thin content (<300 words) struggles to rank -- expand with substantive, unique copy." if page.word_count < 300 else None,
    ))

    vitals_finding, vitals_detail_source = _web_vitals_finding(page)
    findings.append(vitals_finding)

    passed_count = sum(1 for f in findings if f.passed)
    summary = (
        f"{passed_count}/{len(findings)} SEO checks passed. "
        f"Core Web Vitals source: {vitals_detail_source}."
    )
    return build_category_result("SEO", findings, summary)


def _web_vitals_finding(page: PageData) -> tuple[Finding, str]:
    api_key = os.getenv("PAGESPEED_API_KEY")
    if api_key:
        try:
            resp = httpx.get(
                PSI_ENDPOINT,
                params={"url": page.final_url, "key": api_key, "strategy": "mobile"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            metrics = data.get("loadingExperience", {}).get("metrics", {})
            lcp = metrics.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile")
            cls = metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile")
            perf_score = data.get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score")
            passed = bool(perf_score is not None and perf_score >= 0.5)
            detail = f"Lighthouse performance score: {perf_score}; LCP p75: {lcp} ms; CLS p75: {cls}"
            return Finding(
                check="Core Web Vitals (Google PageSpeed Insights)",
                passed=passed,
                weight=12,
                detail=detail,
                fix="Improve LCP/CLS -- compress hero images, defer non-critical JS, reserve space for layout-shifting elements." if not passed else None,
            ), "Google PageSpeed Insights API"
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # fall through to heuristic

    # Heuristic fallback: no PSI key configured. Approximate "fast enough" with
    # server response time and total page weight, which correlate with real LCP.
    passed = page.response_time_ms < 1500 and page.page_size_bytes < 2_000_000
    detail = (
        f"No PAGESPEED_API_KEY configured -- using proxy metrics: "
        f"response time {page.response_time_ms} ms, page weight {page.page_size_bytes / 1024:.0f} KB"
    )
    return Finding(
        check="Core Web Vitals (heuristic proxy)",
        passed=passed,
        weight=12,
        detail=detail,
        fix="Response time and/or page weight are high -- this usually drags down LCP. Set PAGESPEED_API_KEY for a real Lighthouse measurement." if not passed else None,
    ), "heuristic (response time + page weight)"
