"""FastAPI backend: one endpoint that runs the full analysis, plus static UI hosting."""
from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from app.analyzer import analyze_url  # noqa: E402 (must follow load_dotenv)
from app.scraper import FetchError  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Web Vitals & Search Visibility Analyzer", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/analyze can trigger a paid LLM call (GEO scoring) and is reachable by
# anyone once this app is deployed publicly, with no login. These two limits
# bound worst-case API spend from that: a per-visitor cap so no single client
# can hammer it, and a global daily cap so many distinct visitors together
# can't either. In-memory by design -- this is a single-instance demo
# deployment, not a scaled service; a restart resets the counters, which is
# an acceptable tradeoff for the cost protection it buys here.
RATE_LIMIT_PER_IP = 8       # requests
RATE_LIMIT_WINDOW_SEC = 600  # per 10 minutes
GLOBAL_DAILY_LIMIT = 150    # requests across all visitors per UTC day

_ip_requests: dict[str, list[float]] = defaultdict(list)
_global_day: str | None = None
_global_count = 0


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limits(request: Request) -> None:
    global _global_day, _global_count

    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _global_day != today:
        _global_day = today
        _global_count = 0
    if _global_count >= GLOBAL_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="Daily analysis limit reached for this demo. Please try again tomorrow.")

    ip = _client_ip(request)
    now = time.time()
    window = _ip_requests[ip]
    while window and now - window[0] > RATE_LIMIT_WINDOW_SEC:
        window.pop(0)
    if len(window) >= RATE_LIMIT_PER_IP:
        raise HTTPException(status_code=429, detail="Too many requests -- please wait a few minutes and try again.")

    window.append(now)
    _global_count += 1


class AnalyzeRequest(BaseModel):
    url: str


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, request: Request):
    _check_rate_limits(request)
    try:
        report = analyze_url(req.url)
    except FetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
