"""HTML and Markdown image extraction.

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import dataclasses
import re
from html.parser import HTMLParser

# Sentinel for "attribute absent". Using None would be ambiguous with alt="".
ALT_MISSING = object()


@dataclasses.dataclass
class ImageRef:
    """One image found in a file."""

    file: str
    src: str
    alt: object  # str, "" or ALT_MISSING
    line: int
    format: str  # "html" or "markdown"
    kind: str  # "img", "area", "input", "markdown", "markdown-ref"

    def has_alt_text(self) -> bool:
        return isinstance(self.alt, str) and self.alt.strip() != ""


class _ImgParser(HTMLParser):
    def __init__(self, filename: str):
        super().__init__(convert_charrefs=True)
        self.filename = filename
        self.images: list[ImageRef] = []

    def _record(self, kind: str, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k.lower(): (v or "") for k, v in attrs}
        relevant = {
            "img": True,
            "area": bool(d.get("href")),
            "input": d.get("type", "").lower() == "image",
        }.get(kind, False)
        if not relevant:
            return
        self.images.append(
            ImageRef(
                file=self.filename,
                src=d.get("src", ""),
                alt=d["alt"] if "alt" in d else ALT_MISSING,
                line=self.getpos()[0],
                format="html",
                kind=kind,
            )
        )

    def handle_starttag(self, tag, attrs):
        if tag in ("img", "area", "input"):
            self._record(tag, tag, attrs)

    # <img> etc. are void elements, but be safe with XML-ish input
    handle_startendtag = handle_starttag


def parse_html(text: str, filename: str) -> list[ImageRef]:
    p = _ImgParser(filename)
    p.feed(text)
    p.close()
    return p.images


_MD_INLINE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\(\s*(?P<src>[^)\s]+)(?:\s+\"(?P<title>[^\"]*)\")?\s*\)"
)
_MD_REF_SRC_RE = re.compile(r"^\s*!\[(?P<alt>[^\]]*)\]\[(?P<label>[^\]]*)\]\s*$")
_MD_REF_DEF_RE = re.compile(r"^\s*\[(?P<label>[^\]]+)\]:\s+(?P<src>\S+)")


def parse_markdown(text: str, filename: str) -> list[ImageRef]:
    images: list[ImageRef] = []
    lines = text.splitlines()
    # Collect reference-style definitions [label]: src
    refs: dict[str, str] = {}
    for line in lines:
        m = _MD_REF_DEF_RE.match(line)
        if m:
            refs[m.group("label").strip().lower()] = m.group("src")
    # Strip fenced code blocks so code samples don't count
    body_lines: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            body_lines.append((i, line))
    for lineno, line in body_lines:
        for m in _MD_INLINE_RE.finditer(line):
            images.append(
                ImageRef(filename, m.group("src"), m.group("alt"), lineno, "markdown", "markdown")
            )
        m = _MD_REF_SRC_RE.match(line)
        if m:
            label = m.group("label").strip().lower() or m.group("label")
            src = refs.get(label, "")
            images.append(
                ImageRef(filename, src, m.group("alt"), lineno, "markdown", "markdown-ref")
            )
    return images


def parse_file(path: str, content: str) -> list[ImageRef]:
    """Dispatch on file extension."""
    lowered = path.lower()
    if lowered.endswith((".md", ".markdown", ".mdx")):
        return parse_markdown(content, path)
    if lowered.endswith((".html", ".htm", ".xhtml")):
        return parse_html(content, path)
    # Guess by content: HTML-ish if it contains a doctype or <html
    head = content[:512].lower()
    if "<html" in head or "<!doctype html" in head or "<img" in head:
        return parse_html(content, path)
    return parse_markdown(content, path)
