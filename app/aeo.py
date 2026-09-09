"""AEO: direct-answer extractability -- structured data, Q&A patterns, and
featured-snippet-friendly formatting (lists, tables, short direct answers).
"""
from __future__ import annotations

import re

from app.models import Finding
from app.scoring import build_category_result, shorten
from app.scraper import PageData

SNIPPET_WORTHY_TYPES = {
    "FAQPage", "QAPage", "HowTo", "Article", "NewsArticle", "BlogPosting",
    "Product", "LocalBusiness", "Organization", "Recipe", "Review", "Event",
}


def analyze_aeo(page: PageData):
    findings: list[Finding] = []
    schema_types = _schema_types(page)

    findings.append(Finding(
        check="Schema.org structured data present",
        passed=len(schema_types) > 0,
        weight=10,
        detail=f"Types found: {sorted(schema_types) or '(none)'}",
        fix="Add JSON-LD structured data (Organization, Article, or FAQPage at minimum) so answer engines can parse the page reliably." if not schema_types else None,
    ))

    has_faq_schema = "FAQPage" in schema_types
    findings.append(Finding(
        check="FAQPage schema present",
        passed=has_faq_schema,
        weight=8,
        detail="FAQPage schema found" if has_faq_schema else "No FAQPage schema",
        fix="If the page has Q&A content, mark it up with FAQPage schema -- this is the single highest-leverage AEO win for featured snippets." if not has_faq_schema else None,
    ))

    has_howto_schema = "HowTo" in schema_types
    question_headings = [h for _, h in page.headings_all if h.strip().endswith("?")]
    question_preview = [shorten(h) for h in question_headings[:5]]
    findings.append(Finding(
        check="Question-style headings (snippet bait)",
        passed=len(question_headings) > 0,
        weight=8,
        detail=f"{len(question_headings)} heading(s) phrased as questions: {question_preview}",
        fix="Rephrase key H2/H3 headings as the exact questions users ask (e.g. 'How much does X cost?') -- this is what gets pulled into answer boxes." if not question_headings else None,
    ))

    short_answer_score = _short_answer_after_heading_ratio(page)
    findings.append(Finding(
        check="Direct answers follow headings",
        passed=short_answer_score >= 0.3,
        weight=10,
        detail=f"{short_answer_score:.0%} of headings are followed by a concise (<=50 word) direct-answer paragraph",
        fix="Put a 1-3 sentence direct answer immediately after each question heading, before any elaboration -- this is what gets extracted verbatim into answer boxes." if short_answer_score < 0.3 else None,
    ))

    lists = page.soup.find_all(["ul", "ol"])
    tables = page.soup.find_all("table")
    findings.append(Finding(
        check="List/table formatting for extractable content",
        passed=len(lists) + len(tables) > 0,
        weight=6,
        detail=f"{len(lists)} list(s), {len(tables)} table(s)",
        fix="Convert step-by-step or comparison content into <ul>/<ol>/<table> markup -- these are the formats answer engines extract into rich results." if len(lists) + len(tables) == 0 else None,
    ))

    definitional = _definitional_sentence_count(page)
    findings.append(Finding(
        check="Definitional sentences (\"X is...\", \"X refers to...\")",
        passed=definitional > 0,
        weight=6,
        detail=f"{definitional} definitional sentence(s) detected",
        fix="Add at least one clear definitional sentence (e.g. '[Term] is a ...') near the top -- this pattern is heavily favored for definition snippets." if definitional == 0 else None,
    ))

    has_business_schema = bool({"LocalBusiness", "Organization", "Product"} & schema_types)
    findings.append(Finding(
        check="Entity schema (Organization/LocalBusiness/Product)",
        passed=has_business_schema,
        weight=8,
        detail="Present" if has_business_schema else "Missing",
        fix="Add Organization or LocalBusiness schema with name, address, and contact info -- answer engines use this to attribute answers to your brand." if not has_business_schema else None,
    ))

    passed_count = sum(1 for f in findings if f.passed)
    summary = f"{passed_count}/{len(findings)} AEO checks passed. Schema types detected: {sorted(schema_types) or 'none'}."
    return build_category_result("AEO", findings, summary)


def _schema_types(page: PageData) -> set[str]:
    types: set[str] = set()
    for obj in page.json_ld:
        t = obj.get("@type")
        if isinstance(t, list):
            types.update(t)
        elif isinstance(t, str):
            types.add(t)
    return types


def _short_answer_after_heading_ratio(page: PageData) -> float:
    """Rough heuristic: for each heading tag, does the very next sibling
    paragraph give a concise answer (<=50 words) rather than a long runup?
    """
    headings = page.soup.find_all(re.compile("^h[1-4]$"))
    if not headings:
        return 0.0
    hits = 0
    for h in headings:
        sib = h.find_next_sibling()
        while sib is not None and sib.name in ("script", "style"):
            sib = sib.find_next_sibling()
        if sib and sib.name == "p":
            words = len(sib.get_text(strip=True).split())
            if 0 < words <= 50:
                hits += 1
    return hits / len(headings)


def _definitional_sentence_count(page: PageData) -> int:
    pattern = re.compile(r"\b[A-Z][\w\s'-]{2,40}\s(is|are|refers to|means)\s(a|an|the|to)\b")
    return len(pattern.findall(page.visible_text))
