# alt-text-writer

An accessibility CLI that scans your HTML and Markdown for images **missing alt
text**, proposes concise descriptive alternatives, and applies edits only after
you review a patch.

Built by [Dylan Asdale](https://dylanasdale.github.io) and published by
**Asdale Dynamics, LLC** as part of a suite of beginner-friendly, local-first AI
tools. Plain English, step by step, never condescending.

## Why

Alt text is one of the highest-impact accessibility wins on any website: screen
readers read it, search engines index it, and links and buttons need it. It is
also the easiest thing to forget. This tool finds every image without alt text
and drafts text for you, using local signals first (filename, dimensions in the
name, the nearest heading, captions) so the whole thing works offline.

## Features

- **Parses HTML and Markdown** — `<img>`, `<area>`, `<input type="image">`,
  `![inline](src)`, and reference-style `![alt][ref]` images. Fenced code
  blocks are ignored.
- **Lists every image missing alt text** — including blank `alt=""` when the
  image is not decorative, placeholder values like `alt="TODO"`, and filenames
  pasted in as alt.
- **Heuristic proposals first** — nearest heading, page title, captions, and
  cleanups of the filename (`brown-teacup-800x600.jpg` → "Brown teacup").
- **Optional refinement pass** — send current proposals to any
  OpenAI-compatible chat endpoint to polish descriptions. Defaults to local
  Ollama at `http://localhost:11434/v1`; pass any `--base-url`/`--model`. The
  CLI never sends or asks for an API key; if your endpoint needs auth, supply
  the header value yourself via `--auth-header` (read from your own
  environment — it is never stored or logged).
- **Review before applying** — `fix` prints a unified diff and asks `y/N`.
  Nothing is written until you approve.
- **Decorative-image detector** — flags likely decorative images (spacers,
  1x1 pixels, dividers, arrows) so they get `alt=""` guidance instead of fake
  descriptions.

## Install

Requires Python 3.9+.

```bash
pip install .
```

## Usage

```bash
# List images missing alt text, with proposed text
alt-text-writer scan site/

# Everything as JSON
alt-text-writer scan site/ --json

# Show a patch of proposed alt text, review it, then apply
alt-text-writer fix site/ --dry-run
alt-text-writer fix site/

# Decide for yourself when prompted: y or n
```

Refinement via a local Ollama (or any OpenAI-compatible endpoint):

```bash
# Default endpoint
alt-text-writer fix site/ --base-url http://localhost:11434/v1 --model llama3.2

# Skip LLM entirely
alt-text-writer fix site/ --no-llm
```

JSON report:

```bash
alt-text-writer report site/ --json --output alt-text-report.json
```

Exit codes: `0` = all clear, `1` = discarded/no-op, `2` = missing alt text
found (scan command).

## How proposals are made

1. Nearest heading before the image (or the first heading if none precede it)
2. Page `<title>` / front-matter `title:`
3. Nearby `<figcaption>` or italic caption line
4. Humanized filename words (hashes, dates, and size suffixes stripped)
5. Last resort: a generic but non-empty proposal ("An image."), so you never
   ship an empty alt without knowing

Heuristics are honest, not magic: they are a starting point you confirm,
especially with `--no-llm`. The optional LLM pass only *polishes* one line; it
is told not to invent details.

## Decorative images

Images that are purely decoration should be marked `alt=""` (empty), *not*
given fake descriptions. The detector flags likely decorative images —
spacers, divider/border/shadow assets, 1x1 pixels, plain bullet arrows. They
appear in scan output with a `~decorative` tag.

## Privacy and secrets

- Local-first: heuristics need no network. The LLM pass is optional and
  defaults to localhost Ollama.
- No API keys are requested, read, stored, or logged. Authentication is only
  applied if *you* pass a full `Authorization` header value via `--auth-header`
  (e.g. from your shell environment).
- The tool sends only image filenames and nearby heading/caption text to the
  endpoint you configure.

## Testing

```bash
pip install .[dev]
pytest
```

Tests include HTML/Markdown fixtures and a mocked OpenAI-compatible endpoint
(no network access is used in tests).

## License

MIT — Copyright (c) 2026 Asdale Dynamics, LLC
