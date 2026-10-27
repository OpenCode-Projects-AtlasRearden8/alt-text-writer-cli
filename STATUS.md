# STATUS.md — alt-text-writer

## What was built

`alt-text-writer` is a local-first, Python-only (stdlib core) accessibility CLI
that scans HTML and Markdown files for images missing alt text, proposes
concise descriptive text, shows a reviewable unified diff, and applies edits
only after confirmation.

Components (in `alt_text_writer/`):

- `parser.py` — HTML (`<img>`, `<area>`, `<input type="image">`) via
  `html.parser` plus Markdown inline, reference-style, fenced-code-skipping
  image extraction. Handles missing `alt` attribute vs. empty vs. placeholder.
- `heuristics.py` — local proposals (captions > nearest heading > page title >
  humanized filename > generic fallback) and the decorative-image detector
  (spacers, 1x1 pixels, dividers, bullets).
- `context.py` — nearest-heading/title/figcaption-and-Markdown-caption index
  per line, including figcaption→img association inside multi-line `<figure>`s.
- `llm.py` — optional refinement via any OpenAI-compatible `/chat/completions`
  endpoint. Defaults to Ollama at `http://localhost:11434/v1`, model
  `llama3.2`. No API keys are requested or stored; auth only via a
  user-supplied `--auth-header`. Fails soft back to heuristic proposals.
- `patcher.py` — surgical alt insertion/replacement and unified diffs.
- `cli.py` — commands: `scan`, `fix`, `report`; flags `--json`, `--all`,
  `--dry-run`, `--yes`, `--no-llm`, `--base-url`, `--model`, `--auth-header`.

## How to run

```bash
pip install .          # or: pip install ".[dev]"
alt-text-writer scan path/ --json    # list missing alt text + proposals
alt-text-writer fix path/ --dry-run  # preview patch, write nothing
alt-text-writer fix path/            # review diff, y/N to apply
alt-text-writer report path/ --json --output alt-text-report.json
```

Requires Python 3.9+. No external runtime dependencies; `pytest` for dev.

## Verification results

- `pytest`: **22 passed** (tests/test_cli.py) — parser (HTML/Markdown, fences,
  ref-style), heuristics (priority, humanizing, decorative detection, filename
  alts), patcher (insert/replace/diff), CLI end-to-end on fixtures
  (`tests/fixtures/sample_site/`), and mocked OpenAI-compatible endpoint
  (refinement order, DECORATIVE marker, fail-soft on unreachable URL, mocked
  endpoint in `fix`).
- Manual verification: `scan`, `report`, and `fix --dry-run` all run on the
  fixture site and produce correct proposals (heading for sunrise image,
  figcaption text for pruners, filename-derived fallbacks).
- Package builds and installs cleanly into a fresh venv;
  `alt-text-writer --version` = `0.1.0`.

## Known gaps

- Heuristic proposals are intentionally conservative: without the LLM pass
  they use page context, so unrelated images under one heading can get the
  same text. Confirm/suppress in the Diff review (discard all) and rerun with
  a local model for better descriptions.
- `fix` prompt applies all-at-once per run (no per-image y/n); use
  `--dry-run`, edit, and rerun for finer control.
- Dimension detection works via filenames (`800x600`) only; no image file
  decoding.
- Decorative detector is regex/wordlist-based, not visual; it may miss
  decorative images and should not be considered authoritative.
- LLM refinement batches all images in one request; very large scans may need
  batch splitting against stricter rate limits.
- SVG/inline-data URLs are treated like any other src.

No secrets, API keys, or personal data are stored in the repository.
