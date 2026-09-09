"""Top-level orchestrator: URL in, full Report out. Used by both the CLI and the API."""
from __future__ import annotations

from datetime import datetime, timezone

from app.aeo import analyze_aeo
from app.geo import analyze_geo
from app.models import Report
from app.scoring import grade_for, top_actions_from
from app.scraper import PageData, fetch_page
from app.seo import analyze_seo

# Below this word count, a real page (even a bad one) is unusual -- nav,
# footer, and boilerplate alone usually clear it. A page this thin was very
# likely served to us as a bot-wall / login-gate rather than its real content.
THIN_CONTENT_WORDS = 150


def analyze_url(url: str) -> Report:
    page = fetch_page(url)

    seo_result = analyze_seo(page)
    aeo_result = analyze_aeo(page)
    geo_result, llm_provider = analyze_geo(page)

    overall_score = round((seo_result.score + aeo_result.score + geo_result.score) / 3)
    top_actions = top_actions_from([seo_result, aeo_result, geo_result])

    return Report(
        url=url,
        final_url=page.final_url,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        overall_score=overall_score,
        overall_grade=grade_for(overall_score),
        seo=seo_result,
        aeo=aeo_result,
        geo=geo_result,
        llm_provider=llm_provider,
        top_actions=top_actions,
        content_warning=_detect_content_warning(page),
    )


def _detect_content_warning(page: PageData) -> str | None:
    needs_js = len(page.noscript_text) > 20
    thin = page.word_count < THIN_CONTENT_WORDS

    if needs_js and thin:
        return (
            f"This page returned only {page.word_count} words of visible text and includes a "
            "<noscript> fallback, which strongly suggests the real page requires JavaScript to "
            "render. This tool only reads the initial server-sent HTML (no browser execution), "
            "so the scores below likely reflect a bot-wall or loading shell -- not what a human "
            "visitor actually sees. Common on social platforms and JS single-page apps."
        )
    if needs_js:
        return (
            "This page includes a <noscript> fallback, indicating it may rely on JavaScript to "
            "render its real content. This tool only reads server-sent HTML, so some content may "
            "be missing from the analysis below."
        )
    if thin:
        return (
            f"This page returned only {page.word_count} words of visible text -- unusually thin "
            "for a real page. If this doesn't match what you see in a browser, the site may be "
            "showing a login wall, bot-detection page, or a JavaScript-rendered shell to "
            "non-browser requests rather than its real content."
        )
    return None
