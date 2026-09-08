"""Top-level orchestrator: URL in, full Report out. Used by both the CLI and the API."""
from __future__ import annotations

from datetime import datetime, timezone

from app.aeo import analyze_aeo
from app.geo import analyze_geo
from app.models import Report
from app.scoring import grade_for, top_actions_from
from app.scraper import fetch_page
from app.seo import analyze_seo


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
    )
