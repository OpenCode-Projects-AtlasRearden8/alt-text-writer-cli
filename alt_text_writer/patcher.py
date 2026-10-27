"""Reviewable line edits: build alt-text replacements as verified diffs.

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import dataclasses
import difflib
import re

from .parser import ImageRef


@dataclasses.dataclass
class Edit:
    path: str
    line: int
    old_line: str
    new_line: str
    src: str


def apply_alt_to_lines(content: str, img: ImageRef, alt: str, is_html: bool) -> str:
    """Return full-file content with alt text replaced/inserted on one line."""
    lines = content.splitlines(keepends=True)
    idx = img.line - 1
    if idx >= len(lines):
        return content
    line = lines[idx]
    if is_html:
        m = re.search(r'alt=(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', line, re.IGNORECASE)
        if m:
            line = line[: m.start()] + f'alt="{alt}"' + line[m.end() :]
        else:
            src_m = re.search(r'src=(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', line, re.IGNORECASE)
            ins = f' alt="{alt}"'
            if src_m:
                line = line[: src_m.end()] + ins + line[src_m.end() :]
            elif ">" in line:
                cut = line.index(">")
                line = line[:cut] + ins + line[cut:]
    else:
        # Markdown: ![alt](src) or ![alt][ref]
        new = re.sub(
            r"!\[[^\]]*\](\[[^\]]*\]\([^)]*\)|\([^)]*\)|\[[^\]]*\])",
            f"![{alt}]" + r"\1",
            line,
            count=1,
        )
        line = new
    lines[idx] = line
    return "".join(lines)


def make_patch(path: str, original: str, updated: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
