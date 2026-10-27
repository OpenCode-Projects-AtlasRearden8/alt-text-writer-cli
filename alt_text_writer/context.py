"""Local context extraction: headings, captions, titles near an image line.

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import re
from pathlib import Path

_HTML_HEADING_RE = re.compile(
    r"<(h[1-6])\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL
)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_HTML_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE)
_HTML_CAPTION_RE = re.compile(
    r"<figcaption\b[^>]*>(.*?)</figcaption>", re.IGNORECASE | re.DOTALL
)
_MD_ITALIC_CAPTION_RE = re.compile(r"^\s*[_*]([^_*]+)[_*]\s*$")
_TAG_RE = re.compile(r"<[^>]+>")
_HTML_IMG_RE = re.compile(r"<\s*img\b", re.IGNORECASE)


def _clean(text: str) -> str:
    return " ".join(_TAG_RE.sub(" ", text).split())


def build_context_index(content: str, is_html: bool) -> dict:
    """Returns {"lines": {lineno: context}, "title": str} for fast lookup."""
    lines = content.splitlines()
    headings: list[tuple[int, str]] = []  # (lineno, text)
    if is_html:
        for m in _HTML_HEADING_RE.finditer(content):
            line = content.count("\n", 0, m.start()) + 1
            headings.append((line, _clean(m.group(2))))
        title = _clean(_HTML_TITLE_RE.search(content).group(1)) if _HTML_TITLE_RE.search(content) else ""
        captions_at = {}
        for m in _HTML_CAPTION_RE.finditer(content):
            line = content.count("\n", 0, m.start()) + 1
            captions_at[line] = _clean(m.group(1))
        # Associate figcaptions with the <img> inside the same <figure>, even
        # when the figure spans multiple lines.
        for m in re.finditer(r"<figure\b[^>]*>(.*?)</figure>", content, re.IGNORECASE | re.DOTALL):
            figcap = _HTML_CAPTION_RE.search(m.group(1))
            if not figcap:
                continue
            caption_text = _clean(figcap.group(1))
            for im in _HTML_IMG_RE.finditer(m.group(1)):
                line = content.count("\n", 0, m.start() + im.start()) + 1
                captions_at[line] = caption_text
    else:
        for i, ln in enumerate(lines, 1):
            m = _MD_HEADING_RE.match(ln)
            if m:
                headings.append((i, m.group(2).strip()))
        m = _MD_TITLE_RE.search(content)
        title = m.group(1).strip("'\" ") if m else ""
        captions_at = {}
        for i, ln in enumerate(lines, 1):
            m2 = _MD_ITALIC_CAPTION_RE.match(ln)
            if m2:
                captions_at[i] = m2.group(1).strip()

    def nearest_heading(lineno: int) -> str:
        before = [t for l, t in headings if l <= lineno]
        if before:
            return before[-1]
        return headings[0][1] if headings else ""

    # Captions are only trusted when very close: same line for HTML
    # (figcaption belongs inside its own figure), same/next line for
    # Markdown italic captions. Anything further risks stealing captions
    # from neighboring images.
    def nearest_caption(lineno: int, is_html_: bool) -> str:
        if is_html_:
            return captions_at.get(lineno, "")
        for dist in (0, 1):
            hit = captions_at.get(lineno + dist)
            if hit:
                return hit
        return ""

    index: dict = {"title": title, "lines": {}}
    for i in range(1, len(lines) + 2):
        index["lines"][i] = {
            "heading": nearest_heading(i),
            "caption": nearest_caption(i, is_html),
            "title": title,
        }
    return index
