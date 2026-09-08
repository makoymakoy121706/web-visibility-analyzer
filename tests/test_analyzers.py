from app.aeo import analyze_aeo
from app.geo import analyze_geo
from app.scoring import build_category_result, grade_for, top_actions_from
from app.models import Finding
from app.seo import analyze_seo
from tests.conftest import page_from_html

WEAK_HTML = "<html><head></head><body><p>Hi</p></body></html>"

STRONG_HTML = """
<html lang="en">
<head>
  <title>Bay Area Dental Implants -- Cost, Recovery & Financing Guide</title>
  <meta name="description" content="Everything you need to know about dental implant cost, recovery time, and financing options at our Bay Area clinic.">
  <link rel="canonical" href="https://client-site.example/page">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script type="application/ld+json">
  {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}
  </script>
  <script type="application/ld+json">
  {"@context": "https://schema.org", "@type": "LocalBusiness", "name": "Bay Area Dental"}
  </script>
</head>
<body>
  <h1>Dental Implant Cost Guide</h1>
  <h2>How much do dental implants cost?</h2>
  <p>A single implant typically costs $3,000 to $4,500 according to a 2023 ADA survey.</p>
  <h2>What is a dental implant?</h2>
  <p>A dental implant is a titanium post that replaces a missing tooth root.</p>
  <ul><li>Consultation</li><li>Placement</li><li>Healing</li></ul>
  <p>Research from the American Dental Association found that 95% of implants last over 10 years.</p>
  <p>According to the study, recovery averages 3-6 months for full osseointegration.</p>
  <a href="https://ada.org/study">ADA study</a>
  <a href="https://nih.gov/research">NIH research</a>
  <img src="x.jpg" alt="Dental implant diagram">
</body>
</html>
"""


def test_weak_page_fails_most_seo_checks():
    page = page_from_html(WEAK_HTML)
    result = analyze_seo(page)
    assert result.score < 50
    failed_checks = {f.check for f in result.findings if not f.passed}
    assert "Title tag present and well-sized" in failed_checks
    assert "Meta description present and well-sized" in failed_checks


def test_strong_page_scores_well_on_seo_and_aeo():
    page = page_from_html(STRONG_HTML)
    seo = analyze_seo(page)
    aeo = analyze_aeo(page)
    assert seo.score >= 60
    assert aeo.score >= 60
    faq_finding = next(f for f in aeo.findings if f.check == "FAQPage schema present")
    assert faq_finding.passed


def test_geo_heuristic_fallback_runs_without_llm_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    page = page_from_html(STRONG_HTML)
    result, provider = analyze_geo(page)
    assert provider.startswith("heuristic")
    assert 0 <= result.score <= 100
    assert len(result.findings) == 7  # 4 programmatic + 3 heuristic LLM-substitute checks


def test_scoring_weights_drive_percentage_correctly():
    findings = [
        Finding(check="a", passed=True, weight=10, detail=""),
        Finding(check="b", passed=False, weight=10, detail="", fix="do b"),
    ]
    result = build_category_result("TEST", findings, "summary")
    assert result.score == 50
    assert result.grade == grade_for(50)


def test_top_actions_dedupes_and_ranks_by_weight():
    findings_a = [Finding(check="a", passed=False, weight=5, detail="", fix="fix-low")]
    findings_b = [Finding(check="b", passed=False, weight=10, detail="", fix="fix-high")]
    dupe = [Finding(check="c", passed=False, weight=3, detail="", fix="fix-high")]
    result_a = build_category_result("A", findings_a, "s")
    result_b = build_category_result("B", findings_b, "s")
    result_c = build_category_result("C", dupe, "s")
    actions = top_actions_from([result_a, result_b, result_c], limit=5)
    assert actions[0] == "fix-high"
    assert actions.count("fix-high") == 1


def test_fetch_error_raised_for_bad_domain():
    from app.scraper import FetchError, fetch_page
    import pytest
    with pytest.raises(FetchError):
        fetch_page("https://this-domain-should-not-exist-12345.invalid", timeout=5.0)
