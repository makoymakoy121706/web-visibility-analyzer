"""GEO: generative-engine visibility -- brand citation signals, entity authority,
quote/stat density, and LLM readability. Programmatic checks run first (density
counts, source links); the qualitative judgment (would an LLM actually cite this
page?) is delegated to an LLM call with a structured-JSON prompt, with a
deterministic heuristic fallback when no LLM key is configured.
"""
from __future__ import annotations

import re

from app.llm_client import LLMUnavailable, call_llm_json, get_active_provider
from app.models import Finding
from app.scoring import build_category_result
from app.scraper import PageData

STAT_PATTERN = re.compile(r"\b\d+(\.\d+)?\s?(%|percent|x|million|billion|thousand)?\b", re.I)
QUOTE_PATTERN = re.compile(r"[“\"][^”\"]{15,300}[”\"]")
SOURCE_WORDS = re.compile(r"\b(according to|source:|study by|research (from|by)|cited by|via)\b", re.I)

MAX_CONTENT_CHARS = 6000  # keep prompts small and fast on free-tier rate limits

_AXIS_SCHEMA = {
    "type": "object",
    "properties": {
        # 0-10 is enforced by prompt text + _clamp_score(), not JSON Schema --
        # Anthropic's structured-output schema subset rejects numeric
        # minimum/maximum on integer properties (400 invalid_request_error).
        "score": {"type": "integer"},
        "reasoning": {"type": "string"},
        "improvement": {"type": "string"},
    },
    "required": ["score", "reasoning", "improvement"],
    "additionalProperties": False,
}

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_authority": _AXIS_SCHEMA,
        "llm_readability": _AXIS_SCHEMA,
        "citation_worthiness": _AXIS_SCHEMA,
    },
    "required": ["entity_authority", "llm_readability", "citation_worthiness"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are an expert in Generative Engine Optimization (GEO) -- evaluating whether "
    "AI assistants like ChatGPT, Claude, and Perplexity would cite a webpage as a source "
    "in a generated answer. You are strict and evidence-based, not encouraging. "
    "Always respond with ONLY a JSON object matching the requested schema, no prose."
)


def analyze_geo(page: PageData):
    findings: list[Finding] = []

    quotes = QUOTE_PATTERN.findall(page.visible_text)
    stat_matches = [m for m in STAT_PATTERN.finditer(page.visible_text) if m.group(2)]
    density = (len(quotes) + len(stat_matches)) / max(page.word_count, 1) * 1000
    findings.append(Finding(
        check="Quotation & statistic density",
        passed=density >= 3,
        weight=10,
        detail=f"{len(quotes)} quotes, {len(stat_matches)} quantified stats ({density:.1f} per 1,000 words)",
        fix="Add concrete, quotable statistics and expert quotes -- LLMs preferentially cite pages with specific, extractable facts over generic prose." if density < 3 else None,
    ))

    source_mentions = len(SOURCE_WORDS.findall(page.visible_text))
    findings.append(Finding(
        check="Source attribution language",
        passed=source_mentions > 0,
        weight=6,
        detail=f"{source_mentions} attribution phrase(s) found (e.g. 'according to', 'study by')",
        fix="Attribute claims to named sources ('according to [Study/Org]') -- this is a strong signal of the trustworthiness LLMs weight when selecting citations." if source_mentions == 0 else None,
    ))

    external_authority_links = len(page.external_links)
    findings.append(Finding(
        check="Outbound links to authoritative sources",
        passed=external_authority_links >= 2,
        weight=6,
        detail=f"{external_authority_links} external link(s)",
        fix="Link out to authoritative external sources (studies, official docs, .gov/.edu) -- pages embedded in a citation graph are favored by generative engines." if external_authority_links < 2 else None,
    ))

    schema_org_types = {t for obj in page.json_ld for t in ([obj.get("@type")] if isinstance(obj.get("@type"), str) else obj.get("@type") or [])}
    has_entity_schema = bool({"Organization", "Person", "LocalBusiness"} & schema_org_types)
    findings.append(Finding(
        check="Named entity schema (brand/author identity)",
        passed=has_entity_schema,
        weight=6,
        detail="Present" if has_entity_schema else "Missing",
        fix="Add Organization/Person schema so LLMs can resolve 'who is speaking' -- entity clarity is a prerequisite for brand citation." if not has_entity_schema else None,
    ))

    llm_findings, provider_used = _llm_readability_findings(page)
    findings.extend(llm_findings)

    passed_count = sum(1 for f in findings if f.passed)
    summary = f"{passed_count}/{len(findings)} GEO checks passed. Qualitative scoring via: {provider_used}."
    return build_category_result("GEO", findings, summary), provider_used


def _llm_readability_findings(page: PageData) -> tuple[list[Finding], str]:
    content = page.visible_text[:MAX_CONTENT_CHARS]
    user_prompt = (
        f"Page title: {page.title}\n"
        f"Page URL: {page.final_url}\n\n"
        f"Page content (truncated to {MAX_CONTENT_CHARS} chars):\n\"\"\"\n{content}\n\"\"\"\n\n"
        "Score this page on three 0-10 integer scales for how likely a generative AI "
        "search engine (ChatGPT, Perplexity, Gemini) would cite it as a source, and give "
        "one specific, actionable improvement for each. Return ONLY this JSON schema:\n"
        "{\n"
        '  "entity_authority": {"score": <0-10>, "reasoning": "<one sentence>", "improvement": "<one sentence>"},\n'
        '  "llm_readability": {"score": <0-10>, "reasoning": "<one sentence>", "improvement": "<one sentence>"},\n'
        '  "citation_worthiness": {"score": <0-10>, "reasoning": "<one sentence>", "improvement": "<one sentence>"}\n'
        "}"
    )

    provider = get_active_provider()
    if provider != "heuristic":
        try:
            # json_schema is enforced server-side on Anthropic (structured outputs);
            # other providers get it as prompt text only, and _findings_from_llm_result
            # raises KeyError below if they don't actually follow it -- which is caught
            # here and falls through to the heuristic rather than reporting fabricated
            # zero scores for a schema the model silently ignored.
            result = call_llm_json(SYSTEM_PROMPT, user_prompt, json_schema=RESULT_SCHEMA)
            return _findings_from_llm_result(result, provider), provider
        except (LLMUnavailable, KeyError, TypeError, ValueError):
            pass  # fall through to heuristic below; provider had a key but the call failed

    return _heuristic_readability_findings(page), "heuristic (no LLM key configured, or call failed)"


def _findings_from_llm_result(result: dict, provider: str) -> list[Finding]:
    findings = []
    labels = {
        "entity_authority": "Entity authority (LLM-judged)",
        "llm_readability": "LLM readability (LLM-judged)",
        "citation_worthiness": "Citation worthiness (LLM-judged)",
    }
    for key, label in labels.items():
        item = result[key]  # KeyError here -> caller falls back to heuristic
        score = max(0, min(10, int(item["score"])))
        passed = score >= 6
        reasoning = item.get("reasoning", "")
        improvement = item.get("improvement", "")
        findings.append(Finding(
            check=label,
            passed=passed,
            weight=8,
            detail=f"{score}/10 via {provider} -- {reasoning}",
            fix=improvement if not passed and improvement else None,
        ))
    return findings


def _heuristic_readability_findings(page: PageData) -> list[Finding]:
    """No-LLM fallback: approximates the three qualitative scores from structural
    signals already extracted (headings, schema, sentence length) so the app
    still produces a full report with zero external dependencies.
    """
    sentences = re.split(r"(?<=[.!?])\s+", page.visible_text)
    avg_sentence_len = (sum(len(s.split()) for s in sentences) / len(sentences)) if sentences else 0
    readable = 8 <= avg_sentence_len <= 22

    has_headings = len(page.headings_all) >= 3
    has_schema = len(page.json_ld) > 0

    findings = [
        Finding(
            check="Entity authority (heuristic)",
            passed=has_schema,
            weight=8,
            detail=f"Structured data {'present' if has_schema else 'absent'} -- used as a proxy for resolvable brand identity",
            fix="Configure an LLM API key (GROQ_API_KEY recommended, free tier) for a real qualitative authority assessment, and add entity schema in the meantime." if not has_schema else None,
        ),
        Finding(
            check="LLM readability (heuristic)",
            passed=readable,
            weight=8,
            detail=f"Average sentence length: {avg_sentence_len:.1f} words (8-22 is the LLM-friendly band)",
            fix="Break up long sentences -- generative models extract and quote short, self-contained sentences more reliably." if not readable else None,
        ),
        Finding(
            check="Citation worthiness (heuristic)",
            passed=has_headings,
            weight=8,
            detail=f"{len(page.headings_all)} heading(s) -- clear structure correlates with excerptability",
            fix="Add clear H2/H3 section headings so an LLM can isolate and cite a specific section rather than skipping the page." if not has_headings else None,
        ),
    ]
    return findings
