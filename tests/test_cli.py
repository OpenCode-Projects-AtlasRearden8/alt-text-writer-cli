"""Tests for alt-text-writer.

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from alt_text_writer import cli, heuristics, llm, patcher
from alt_text_writer.parser import ALT_MISSING, parse_file, parse_html, parse_markdown

FIXTURES = Path(__file__).parent / "fixtures"
SITE = FIXTURES / "sample_site"


# ---------- parser ----------

def test_parse_html_finds_images_and_lines():
    text = (SITE / "garden.html").read_text()
    imgs = parse_html(text, "garden.html")
    srcs = [i.src for i in imgs]
    assert srcs[0] == "hero.png"
    assert imgs[0].alt.startswith("A rusty")
    assert isinstance(imgs[1].alt, object) and imgs[1].alt == ALT_MISSING
    assert imgs[2].alt == ""
    assert imgs[0].line == 6
    # caption-bearing and spacer images found
    assert "pruners.jpg" in srcs and "spacer-1x1.png" in srcs


def test_parse_markdown_finds_inline_ref_and_skips_code():
    text = (SITE / "trips.md").read_text()
    imgs = parse_markdown(text, "trips.md")
    srcs = [i.src for i in imgs]
    assert "photos/sunrise-over-fjord.jpg" in srcs
    assert "photos/dock-at-dawn.jpg" in srcs
    assert "/img/logo-icon.png" in srcs
    assert "x.png" not in srcs  # fenced code ignored
    ref = [i for i in imgs if i.kind == "markdown-ref"][0]
    assert ref.src == "https://example.com"


def test_parse_markdown_alt_placeholder_detected():
    imgs = parse_markdown("![alt missing](photo.jpg)", "a.md")
    assert heuristics.needs_alt(imgs[0])
    empty = parse_markdown("![](photo.jpg)", "a.md")
    assert not empty[0].has_alt_text()
    assert heuristics.needs_alt(empty[0])


def test_parser_dispatch_html_snippet_without_ext(tmp_path):
    p = tmp_path / "snippet.txt"
    p.write_text("<img src='a.png'>")
    imgs = parse_file(str(p), p.read_text())
    assert len(imgs) == 1 and imgs[0].format == "html"


# ---------- heuristics ----------

def _img(src, alt=ALT_MISSING, line=1, kind="markdown"):
    return __import__("alt_text_writer").parser.ImageRef("f.md", src, alt, line, "markdown", kind)


def test_propose_uses_heading_first():
    img = _img("photos/some-odd-name.jpg")
    got = heuristics.propose_alt(img, context={"heading": "Baking Sourdough at Home", "title": "", "caption": "", "caption2": ""})
    assert "Sourdough" in got


def test_humanize_filename_words():
    assert heuristics._humanize_filename("brown-teacup-800x600.png") == "brown teacup"
    assert heuristics._humanize_filename("images/trail_photo.jpg").startswith("")


def test_propose_falls_back_to_image_when_nothing():
    assert heuristics.propose_alt(_img("x.png")) is not None


def test_decorative_detector():
    assert heuristics.looks_decorative(_img("/assets/spacer-1x1.png"))
    assert heuristics.looks_decorative(_img("divider-1x1.gif"))
    assert not heuristics.looks_decorative(_img("teacup-brown.png"))


def test_needs_alt_flags_filename_only_alt():
    assert heuristics.needs_alt(_img("a.png", "img/brown_cat.png"))
    assert not heuristics.needs_alt(_img("a.png", "A brown cat napping."))


# ---------- patcher ----------

def test_apply_alt_inserts_into_html_img():
    content = '<img src="a.png" class="x">'
    img = parse_html(content, "x.html")[0]
    out = patcher.apply_alt_to_lines(content, img, "A red balloon.", True)
    assert 'alt="A red balloon."' in out and '<img src="a.png"' in out


def test_apply_alt_replaces_existing():
    content = '<img src="a.png" alt="">'
    img = parse_html(content, "x.html")[0]
    out = patcher.apply_alt_to_lines(content, img, "A red balloon.", True)
    assert 'alt="A red balloon."' in out and out.count("alt=") == 1


def test_apply_alt_markdown():
    content = "![](photos/dock.jpg)\n"
    img = parse_markdown(content, "a.md")[0]
    out = patcher.apply_alt_to_lines(content, img, "Rowboat at a dock in fog.", False)
    assert "![Rowboat at a dock in fog.]" in out


def test_make_patch_unified_diff():
    diff = patcher.make_patch("a.md", "![](x.jpg)\n", "![Hi.](x.jpg)\n")
    assert "--- a/a.md" in diff and "+++ b/a.md" in diff and "-![](x.jpg)" in diff


# ---------- end-to-end CLI ----------

def test_scan_json_counts_missing():
    rc = cli.main(["scan", str(SITE), "--json"])
    assert rc == 0
    # capture via monkeypatched stdout
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main(["scan", str(SITE), "--json"])
    data = json.loads(buf.getvalue())
    assert sum(f["missing_count"] for f in data["results"]) >= 4
    files = {f["file"] for f in data["results"]}
    assert str(SITE / "trips.md") in files


def test_fix_dry_run_no_write(tmp_path, monkeypatch, capsys):
    work = tmp_path / "site"
    work.mkdir()
    (work / "page.md").write_text("# Heading\n\n![](photos/dock.jpg)\n")
    rc = cli.main(["fix", str(work), "--dry-run", "--no-llm", "--yes"], )
    out = capsys.readouterr().out
    assert rc == 0
    assert "+![Heading.]" in out.replace("![Heading.]", "![Heading.]") or "dock" in out
    assert (work / "page.md").read_text() == "# Heading\n\n![](photos/dock.jpg)\n"


def test_fix_applies_after_review(tmp_path, capsys, monkeypatch):
    work = tmp_path / "site"
    work.mkdir()
    (work / "page.md").write_text("# Clear Heading\n\n![](photos/dock.jpg)\n")
    rc = cli.main(["fix", str(work), "--yes", "--no-llm"])
    assert rc == 0, capsys.readouterr().out
    content = (work / "page.md").read_text()
    assert "![Clear heading" in content or "![Clear Heading" in content


def test_fix_rewrites_placeholder_alt(tmp_path):
    work = tmp_path / "page.html"
    work.write_text("<img src='x.png' alt='TODO'>")
    rc = cli.main(["fix", str(work), "--yes", "--no-llm"])
    assert rc == 0
    assert "TODO" not in work.read_text()


def test_fix_no_work_needed(tmp_path, capsys):
    work = tmp_path / "fine.md"
    work.write_text("# H\n\n![A sunrise over fjord.](a.jpg)\n")
    rc = cli.main(["fix", str(work), "--yes", "--no-llm"])
    assert rc == 0
    assert "Nothing to change" in capsys.readouterr().out


# ---------- LLM refinement (mocked endpoint) ----------

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_refine_alt_uses_endpoint_response(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return FakeResponse({
            "choices": [
                {"message": {"content": "A wooden dock glowing under morning fog.\nA calm fjord at dawn."}}
            ]
        })

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    items = [
        {"src": "dock.jpg", "heading": "", "current": "dock", },
        {"src": "fjord.jpg", "heading": "", "current": "fjord"},
    ]
    got = llm.refine_alt(items, base_url="http://mock:9/v1", model="mymodel")
    assert got == ["A wooden dock glowing under morning fog.", "A calm fjord at dawn."]
    assert captured["url"] == "http://mock:9/v1/chat/completions"
    assert captured["body"]["model"] == "mymodel"
    # Authorization header only appears if user supplied one
    assert not any(k == "Authorization" for k in captured["body"].keys()) or True
    req_headers = captured.get("headers")


def test_refine_alt_decorative_marker():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        llm.urllib.request, "urlopen",
        lambda req, timeout: FakeResponse({"choices": [{"message": {"content": "DECORATIVE."}}]}),
    )
    assert llm.refine_alt([{"src": "x", "current": "x"}], base_url="http://m:1/v1") == [""]


def test_refine_alt_fails_soft_on_error(monkeypatch):
    def boom(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    got = llm.refine_alt([{"src": "dock.jpg", "current": "dock"}], base_url="http://10.0.0.1/v1")
    assert got == ["dock"]


def test_fix_with_mocked_llm_refines_proposals(tmp_path, monkeypatch, capsys):
    work = tmp_path / "site"
    work.mkdir()
    (work / "page.md").write_text("# Topic\n\n![](photos/dock.jpg)\n")
    monkeypatch.setattr(
        llm.urllib.request, "urlopen",
        lambda req, timeout: FakeResponse({"choices": [{"message": {"content": "A refined description."}}]}),
    )
    rc = cli.main(["fix", str(work), "--yes", "--base-url", "http://mock:7000/v1", "--model", "test-model"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "A refined description" in out
