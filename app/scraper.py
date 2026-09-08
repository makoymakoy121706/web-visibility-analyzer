"""Fetches a URL and extracts every raw signal the SEO/AEO/GEO analyzers need.

One network round-trip, one parse pass. Downstream analyzers only read
from the PageData object below -- they never touch the network.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; VisibilityAnalyzer/1.0; +https://example.com/bot)"


@dataclass
class PageData:
    url: str
    final_url: str
    status_code: int
    html: str
    soup: BeautifulSoup
    response_time_ms: float
    page_size_bytes: int
    headers: dict = field(default_factory=dict)

    # Parsed convenience fields, filled in by _extract()
    title: str = ""
    meta_description: str = ""
    canonical: str | None = None
    viewport: str | None = None
    lang: str | None = None
    h1s: list[str] = field(default_factory=list)
    h2s: list[str] = field(default_factory=list)
    headings_all: list[tuple[str, str]] = field(default_factory=list)  # (tag, text)
    images: list[dict] = field(default_factory=list)  # {src, alt}
    internal_links: list[str] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    json_ld: list[dict] = field(default_factory=list)
    word_count: int = 0
    visible_text: str = ""
    robots_txt_found: bool = False
    sitemap_found: bool = False
    is_https: bool = False


class FetchError(Exception):
    """Raised when the target URL cannot be retrieved at all."""


def fetch_page(url: str, timeout: float = 15.0) -> PageData:
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    start = time.perf_counter()
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach {url}: {exc}") from exc
    elapsed_ms = (time.perf_counter() - start) * 1000

    if resp.status_code >= 400:
        raise FetchError(f"{url} returned HTTP {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    page = PageData(
        url=url,
        final_url=str(resp.url),
        status_code=resp.status_code,
        html=resp.text,
        soup=soup,
        response_time_ms=round(elapsed_ms, 1),
        page_size_bytes=len(resp.content),
        headers=dict(resp.headers),
    )
    _extract(page)
    _check_robots_and_sitemap(page, timeout=timeout)
    return page


def _extract(page: PageData) -> None:
    soup = page.soup
    parsed = urlparse(page.final_url)
    page.is_https = parsed.scheme == "https"

    if soup.title and soup.title.string:
        page.title = soup.title.string.strip()

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta_desc and meta_desc.get("content"):
        page.meta_description = meta_desc["content"].strip()

    canonical_tag = soup.find("link", rel=lambda v: v and "canonical" in v)
    if canonical_tag and canonical_tag.get("href"):
        page.canonical = canonical_tag["href"]

    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    if viewport_tag:
        page.viewport = viewport_tag.get("content")

    html_tag = soup.find("html")
    if html_tag:
        page.lang = html_tag.get("lang")

    for tag in soup.find_all(re.compile("^h[1-6]$")):
        text = tag.get_text(strip=True)
        if not text:
            continue
        page.headings_all.append((tag.name, text))
        if tag.name == "h1":
            page.h1s.append(text)
        elif tag.name == "h2":
            page.h2s.append(text)

    for img in soup.find_all("img"):
        page.images.append({"src": img.get("src", ""), "alt": img.get("alt")})

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        absolute = urljoin(page.final_url, href)
        if urlparse(absolute).netloc == parsed.netloc:
            page.internal_links.append(absolute)
        else:
            page.external_links.append(absolute)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            page.json_ld.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            page.json_ld.append(data)

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    page.visible_text = re.sub(r"\s+", " ", text)
    page.word_count = len(page.visible_text.split())


def _check_robots_and_sitemap(page: PageData, timeout: float) -> None:
    parsed = urlparse(page.final_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            robots_resp = client.get(f"{root}/robots.txt")
            page.robots_txt_found = robots_resp.status_code == 200
            if page.robots_txt_found and "sitemap" in robots_resp.text.lower():
                page.sitemap_found = True
            else:
                sitemap_resp = client.get(f"{root}/sitemap.xml")
                page.sitemap_found = sitemap_resp.status_code == 200
    except httpx.HTTPError:
        pass
