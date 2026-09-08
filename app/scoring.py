"""Turns a list of weighted pass/fail Findings into a 0-100 score and letter grade."""
from __future__ import annotations

from app.models import CategoryResult, Finding


def grade_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def build_category_result(category: str, findings: list[Finding], summary: str) -> CategoryResult:
    total_weight = sum(f.weight for f in findings) or 1
    earned = sum(f.weight for f in findings if f.passed)
    score = round((earned / total_weight) * 100)
    return CategoryResult(
        category=category,
        score=score,
        grade=grade_for(score),
        findings=findings,
        summary=summary,
    )


def top_actions_from(results: list[CategoryResult], limit: int = 5) -> list[str]:
    failed = [f for r in results for f in r.findings if not f.passed and f.fix]
    failed.sort(key=lambda f: f.weight, reverse=True)
    seen: set[str] = set()
    actions: list[str] = []
    for f in failed:
        if f.fix in seen:
            continue
        seen.add(f.fix)
        actions.append(f.fix)
        if len(actions) >= limit:
            break
    return actions
