"""alt-text-writer: find images missing alt text and draft it for you.

Copyright (c) 2026 Asdale Dynamics, LLC. MIT License.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import heuristics
from .context import build_context_index
from .llm import DEFAULT_BASE_URL, DEFAULT_MODEL, refine_alt
from .parser import ALT_MISSING, ImageRef, parse_file
from .patcher import apply_alt_to_lines, make_patch

IMAGE_EXTS = (".html", ".htm", ".xhtml", ".md", ".markdown", ".mdx")


# ---------- scanning ----------

def collect_files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for ext in IMAGE_EXTS:
                out.extend(sorted(f for f in path.rglob(f"*{ext}") if f.is_file()))
        elif path.is_file():
            out.append(path)
        else:
            print(f"warning: skipping missing path {p}", file=sys.stderr)
    # de-dup, keep order
    seen = set()
    unique = []
    for f in out:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            unique.append(f)
    return unique


def scan_files(files: list[Path]) -> list[dict]:
    """Scan files; returns per-file results with images, missing list, decorative flags."""
    results = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        is_html = f.suffix.lower() in (".html", ".htm", ".xhtml") or (
            not f.suffix.lower() in (".md", ".markdown", ".mdx")
            and "<html" in text[:512].lower()
        )
        images = parse_file(str(f), text)
        idx = build_context_index(text, is_html)
        entries = []
        for img in images:
            ctx = idx["lines"].get(img.line, {"heading": "", "caption": "", "title": idx["title"]})
            missing = heuristics.needs_alt(img)
            decorative = heuristics.looks_decorative(img)
            proposal = ""
            if missing and not decorative:
                proposal = heuristics.propose_alt(
                    img, context={k: ctx.get(k) for k in ("heading", "caption", "title")}
                )
            entries.append({
                "line": img.line,
                "src": img.src,
                "alt": None if img.alt == ALT_MISSING else (img.alt if isinstance(img.alt, str) else None),
                "missing": missing,
                "decorative_guess": decorative,
                "proposed_alt": "" if decorative else proposal,
                "heading": ctx.get("heading", ""),
                "caption": ctx.get("caption", ""),
            })
        results.append({
            "file": str(f),
            "format": "html" if is_html else "markdown",
            "images": entries,
            "missing_count": sum(1 for e in entries if e["missing"]),
        })
    return results


# ---------- commands ----------

def cmd_scan(args) -> int:
    files = collect_files(args.paths)
    results = scan_files(files)
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return 0
    total_missing = 0
    for res in results:
        missing = [e for e in res["images"] if e["missing"]]
        if not missing and not args.all:
            continue
        print(f"\n{res['file']}  ({res['format']})")
        imgs = res["images"] if args.all else missing
        for e in imgs:
            flag = "MISSING" if e["missing"] else ("~decorative" if e["decorative_guess"] else "has alt")
            loc = f"{res['file']}:{e['line']}"
            line_out = f"  {loc}  [{flag}]  {e['src'] or '(no src)'}"
            if e["missing"] and e["proposed_alt"]:
                line_out += f"\n      proposal: {e['proposed_alt']}"
            print(line_out)
        total_missing += len(missing)
    print(f"\n{total_missing} image(s) missing alt text across {len(results)} file(s).")
    return 0 if total_missing == 0 else 2


def propose_and_refine(files, base_url, model, use_llm, auth_header=None):
    """Build proposals: heuristics first, optional LLM refinement on top."""
    results = scan_files(files)
    if use_llm:
        items = []
        locs = []
        for res in results:
            for e in res["images"]:
                if not e["missing"]:
                    continue
                items.append({
                    "src": e["src"],
                    "heading": e["heading"],
                    "caption": e["caption"],
                    "current": e["proposed_alt"],
                })
                locs.append((res, e))
        if items:
            revised = refine_alt(items, base_url=base_url, model=model, auth_header=auth_header)
            for (res, e), new in zip(locs, revised):
                if new and new != e["proposed_alt"]:
                    e["proposed_alt"] = new
                    e["refined"] = True
    return results


def cmd_fix(args) -> int:
    files = collect_files(args.paths)
    results = propose_and_refine(
        files,
        base_url=args.base_url,
        model=args.model,
        use_llm=not args.no_llm,
        auth_header=args.auth_header,
    )
    original = {res["file"]: Path(res["file"]).read_text(encoding="utf-8", errors="replace") for res in results}
    updated: dict[str, str] = {}
    diffs: list[str] = []
    for res in results:
        path = res["file"]
        is_html = res["format"] == "html"
        content = original[path]
        for e in res["images"]:
            if not e["missing"] or not e["proposed_alt"]:
                continue
            img = ImageRef(path, e["src"], ALT_MISSING, e["line"], res["format"], "img")
            new_content = apply_alt_to_lines(content, img, e["proposed_alt"], is_html)
            if new_content != content:
                diffs.append(make_patch(path, content, new_content))
                content = new_content
        updated[path] = content

    changed = {p: c for p, c in updated.items() if c != original[p]}
    diffs = []
    for p, c in changed.items():
        diffs.append(make_patch(p, original[p], c))
    diff_text = "".join(diffs)

    if not diff_text:
        print("Nothing to change - all images already have alt text (or none were found).")
        return 0

    print("Proposed changes:\n")
    print(diff_text)

    if args.dry_run:
        print("(dry run: nothing written)")
        return 0

    if args.yes:
        answer = "y"
    else:
        answer = input("\nApply these changes? [y/N] ").strip().lower()
    if answer != "y":
        print("Discarded. Re-run with --yes to skip the prompt.")
        return 1

    written = 0
    for path, content in changed.items():
        Path(path).write_text(content, encoding="utf-8")
        written += 1
    print(f"Applied alt text edits to {written} file(s).")
    return 0


def cmd_report(args) -> int:
    files = collect_files(args.paths)
    results = scan_files(files)
    out = {"repo": str(Path.cwd()), "files": results, "missing_total": sum(r["missing_count"] for r in results)}
    if args.json:
        dest = args.output or "alt-text-report.json"
        Path(dest).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nMissing: {out['missing_total']}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="alt-text-writer",
        description="Find images without alt text and draft concise descriptive alt text.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list images missing alt text (with heuristic proposals)")
    scan.add_argument("paths", nargs="+", help="files or directories to scan")
    scan.add_argument("--json", action="store_true", help="emit raw JSON")
    scan.add_argument("--all", action="store_true", help="list every image, not just missing ones")
    scan.set_defaults(func=cmd_scan)

    fix = sub.add_parser("fix", help="show a patch of proposed alt text and apply after review")
    fix.add_argument("paths", nargs="+")
    fix.add_argument("--dry-run", action="store_true", help="print the patch, write nothing")
    fix.add_argument("--yes", action="store_true", help="skip the y/N confirmation")
    fix.add_argument("--no-llm", action="store_true", help="skip the optional LLM refinement pass")
    fix.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible API base URL")
    fix.add_argument("--model", default=DEFAULT_MODEL, help="chat model name")
    fix.add_argument(
        "--auth-header",
        default=None,
        help="optional pre-built Authorization header value (read from your own env/config, never stored)",
    )
    fix.set_defaults(func=cmd_fix)

    rep = sub.add_parser("report", help="write a JSON report of missing alt text")
    rep.add_argument("paths", nargs="+")
    rep.add_argument("--output", default=None, help="output .json file (defaults to stdout unless --json given)")
    rep.add_argument("--json", action="store_true", help="also write file instead of printing")
    rep.set_defaults(func=cmd_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
