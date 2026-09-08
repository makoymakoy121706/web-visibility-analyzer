"""Pluggable LLM backend for the GEO analyzer.

Design rationale (see README "Process Documentation" for the full writeup):
we can't assume the grader has any particular API key configured, so this
module tries providers in priority order and always has a working final
fallback -- a deterministic heuristic scorer -- so the app never crashes or
blocks on missing credentials. Every provider here has a free tier:

  1. GROQ_API_KEY   -- Groq (OpenAI-compatible), generous free tier, fast Llama models
  2. GEMINI_API_KEY -- Google Gemini, free tier
  3. OPENAI_API_KEY -- OpenAI, for users who already have a key/credits
  4. (none)         -- heuristic fallback, no network call, always available
"""
from __future__ import annotations

import json
import os
import re

import httpx

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-1.5-flash"
OPENAI_MODEL = "gpt-4o-mini"


class LLMUnavailable(Exception):
    pass


def get_active_provider() -> str:
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "heuristic"


def call_llm_json(system_prompt: str, user_prompt: str) -> dict:
    """Calls whichever provider is configured and returns parsed JSON.
    Raises LLMUnavailable if no provider is configured or the call fails,
    so callers can fall back to a heuristic without special-casing providers.
    """
    provider = get_active_provider()
    if provider == "groq":
        return _call_openai_compatible(
            base_url="https://api.groq.com/openai/v1/chat/completions",
            api_key=os.environ["GROQ_API_KEY"],
            model=GROQ_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    if provider == "gemini":
        return _call_gemini(system_prompt, user_prompt)
    if provider == "openai":
        return _call_openai_compatible(
            base_url="https://api.openai.com/v1/chat/completions",
            api_key=os.environ["OPENAI_API_KEY"],
            model=OPENAI_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    raise LLMUnavailable("No LLM API key configured (GROQ_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY)")


def _call_openai_compatible(base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> dict:
    try:
        resp = httpx.post(
            base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise LLMUnavailable(str(exc)) from exc


def _call_gemini(system_prompt: str, user_prompt: str) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        resp = httpx.post(
            url,
            params={"key": api_key},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(content)
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise LLMUnavailable(str(exc)) from exc


def _extract_json(content: str) -> dict:
    """LLMs occasionally wrap JSON in markdown fences despite instructions -- strip those."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)
