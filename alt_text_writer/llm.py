"""Optional refinement pass via any OpenAI-compatible chat endpoint.

Defaults to Ollama at http://localhost:11434/v1. No API keys are sent; if a
base URL needs an Authorization header the user can supply one via env var
ONLY (never stored, never committed).

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"

SYSTEM_PROMPT = (
    "You write concise, factual alt text for images on a web page. "
    "Given the image source filename and nearby page context, reply with ONE sentence, "
    "at most 16 words, ending with a period. Describe what the image clearly shows "
    "or its function. Do not invent details you cannot infer. "
    "If the image seems decorative, reply exactly: DECORATIVE. "
    "Reply with the alt text only - no quotes, no preamble."
)


def refine_alt(
    items: list[dict],
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    auth_header: str | None = None,
    timeout: float = 60.0,
) -> list[str]:
    """Ask an OpenAI-compatible /chat/completions endpoint to refine alt text.

    `items` is a list of dicts with keys: src, heading, title, current.
    Returns one proposal string per item, in order. On any error, the
    original/current placeholder is kept (the endpoint call fails soft).
    """
    base_url = base_url.rstrip("/")
    proposals: list[str] = []
    batch = [{"src": it.get("src", ""), "heading": it.get("heading", ""), "title": it.get("title", "")} for it in items]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"images": batch}, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, OSError):
        return [it.get("current", "") for it in items]
    # Model may answer for multiple images split by lines
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if len(lines) >= len(items):
        for ln in lines[: len(items)]:
            bare = ln.strip().strip('"`').rstrip(".").strip().upper()
            if bare == "DECORATIVE":
                proposals.append("")  # decorative: client will skip/report
            else:
                proposals.append(ln.strip('"`'))
        return proposals
    # Ambiguous output; keep current proposals rather than guess.
    return [it.get("current", "") for it in items]
