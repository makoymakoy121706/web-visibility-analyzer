"""Builds a PageData object from a raw HTML string, without any network call,
by reusing scraper's own DOM-extraction pass. Every analyzer test starts here.
"""
from bs4 import BeautifulSoup

from app.scraper import PageData, _extract


def page_from_html(html: str, url: str = "https://client-site.example/page") -> PageData:
    soup = BeautifulSoup(html, "html.parser")
    page = PageData(
        url=url,
        final_url=url,
        status_code=200,
        html=html,
        soup=soup,
        response_time_ms=200.0,
        page_size_bytes=len(html.encode()),
    )
    _extract(page)
    return page
