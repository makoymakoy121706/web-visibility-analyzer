"""Shared result types produced by every analyzer and consumed by the CLI/API."""
from __future__ import annotations

from pydantic import BaseModel


class Finding(BaseModel):
    check: str
    passed: bool
    weight: int  # relative importance within its category, used for scoring
    detail: str
    fix: str | None = None  # concrete remediation, only set when passed=False


class CategoryResult(BaseModel):
    category: str  # "SEO" | "AEO" | "GEO"
    score: int  # 0-100
    grade: str  # A-F
    findings: list[Finding]
    summary: str


class Report(BaseModel):
    url: str
    final_url: str
    analyzed_at: str
    overall_score: int
    overall_grade: str
    seo: CategoryResult
    aeo: CategoryResult
    geo: CategoryResult
    llm_provider: str  # which LLM backed the GEO analysis, or "heuristic"
    top_actions: list[str]  # 3-5 highest-leverage fixes across all categories
    content_warning: str | None = None  # set when the fetched HTML looks like a
    # bot-wall/login-gate/JS-shell rather than the page a real visitor sees --
    # the score below is still an accurate grade of what we actually received,
    # it just may not represent the site a human sees in a browser
