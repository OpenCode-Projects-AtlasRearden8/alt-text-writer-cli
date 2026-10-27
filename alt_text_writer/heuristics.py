"""Heuristic alt-text proposals and decorative-image detection.

No network access; these run entirely locally.

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import re
from pathlib import Path

from .parser import ALT_MISSING, ImageRef

_DECORATIVE_HINTS = (
    ("src", ("spacer", "pixel", "blank", "border", "divider", "button_", "icon-")),
    ("name", ()),
)

_TITLEISH_WORDS = {
    "home", "hero", "banner", "header", "footer", "logo", "background",
    "about", "photo", "picture", "image", "img", "screenshot", "site",
}


def looks_decorative(img: ImageRef, context_headings: list[str] | None = None) -> bool:
    """Best-effort guess that an image is purely decorative."""
    src = (img.src or "").lower()
    base = Path(src).stem.lower()
    ext = Path(src).suffix.lower()
    decorative_markers = (
        "spacer", "pixel", "1x1", "transparent", "blank", "divider",
        "border", "shadow", "corner", "glow", "sliver", "rule",
    )
    if any(m in base for m in decorative_markers):
        return True
    if base in {"arrow", "arrow-left", "arrow-right", "bullet", "dot"}:
        return True
    if ext == ".gif" and re.fullmatch(r"(?:[a-z0-9_]*_)?[0-9x]{1,9}", base):
        # things like "1x1.gif" or "x.gif"
        return True
    if re.fullmatch(r"1x1|1px|spacer\d*", base):
        return True
    return False


def _humanize_filename(src: str) -> str:
    base = Path(src.split("?")[0].split("#")[0]).stem
    # strip common hashes/dates: 2024-01, -800x600, final2 etc.
    base = re.sub(r"[-_]?\d{4}[-_]\d{2}[-_]\d{2}", "", base)
    base = re.sub(r"(?:[-_](\d+x\d+))+$", "", base)
    base = re.sub(r"[-_ ]?(final|copy|new|old|v\d+)$", "", base)
    words: list[str] = []
    for part in re.split(r"[-_ ]+", base):
        if part.isdigit() and len(part) > 4:
            continue  # hashed ids
        for tok in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z0-9]+", part):
            w = tok.lower().strip(".-")
            if w:
                words.append(w)
    if not words:
        return ""
    # drop generic noise words at the start
    while words and words[0] in {"img", "image", "images", "photo", "picture", "screenshot", "assets"}:
        words.pop(0)
    return " ".join(words)


def _is_meaningful_filename_phrase(words: str) -> bool:
    if not words:
        return False
    generic = {"img", "image", "photo", "picture", "screenshot", "tab", "banner", "hero"}
    return not (len(words.split()) == 1 and words.lower() in generic)


def propose_alt(img: ImageRef, context: dict | None = None) -> str:
    """Propose alt text using whatever local signals are available.

    `context` may carry keys: heading (nearest preceding heading text),
    title (HTML title or page first heading), dimensions (e.g. "800x600"),
    captions (list of nearby caption strings).
    """
    context = context or {}
    candidates: list[str] = []
    src = img.src or ""
    base = Path(src.split("?")[0].split("#")[0]).stem

    # 1. Captions are the most specific signal for a single image.
    caps = list(context.get("captions", []) or [])
    if context.get("caption"):
        caps.append(context["caption"])
    for cap in caps:
        cap = (cap or "").strip()
        if cap:
            candidates.append(cap)

    # 2. Nearest heading text is usually the best semantic label.
    heading = (context.get("heading") or "").strip()
    if heading and heading.lower() not in _TITLEISH_WORDS:
        candidates.append(heading)

    # 3. Title-ish hints
    title = (context.get("title") or "").strip()
    if title and title.lower() != (img.src or "").strip().lower():
        candidates.append(title)

    # 3. Filename words
    words = _humanize_filename(src)
    if _is_meaningful_filename_phrase(words):
        candidates.append(words)

    # 4. Last resort: dimensions (better than nothing but flags as generic)
    dims = context.get("dimensions") or ""
    if not candidates and dims:
        candidates.append("An image")

    if not candidates:
        if src:
            candidates.append(_humanize_filename(src) or Path(src).name)
        else:
            candidates.append("An image")

    text = candidates[0]
    text = " ".join(text.split())
    if text:
        text = text[0].upper() + text[1:]
        if not text.endswith((".", "!", "?")):
            text += "."
    cap_len = 125
    if len(text) > cap_len:
        text = text[: cap_len - 1].rstrip() + "."
    return text or "An image."


def needs_alt(img: ImageRef) -> bool:
    """Images that should get alt text (missing, em-dash-ish placeholder, filename)."""
    if img.alt == ALT_MISSING:
        return True
    if not isinstance(img.alt, str):
        return True
    alt = img.alt.strip()
    if alt == "":
        return True
    if alt.lower() in {"alt", "todo", "tbd", "placeholder", "alt text", "alt missing", "missing", "image", "no alt"}:
        return True
    # A lone filename as alt adds no value
    if re.fullmatch(r"[\w./\\-]+\.(?:png|jpe?g|gif|svg|webp|avif|bmp|ico)", alt, re.IGNORECASE):
        return True
    return False
