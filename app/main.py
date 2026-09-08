"""FastAPI backend: one endpoint that runs the full analysis, plus static UI hosting."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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


class AnalyzeRequest(BaseModel):
    url: str


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
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
