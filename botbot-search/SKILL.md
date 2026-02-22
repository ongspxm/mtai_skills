---
name: botbot-search
description: Use when you need to search for facts online and return structured results (link, title, description) via a lightweight CLI.
---

# BotBot Search

Lightweight web-search helper using a single Python script.

## What It Does

- Search the web for factual information using a no-key search endpoint.
- Return normalized result items with `link`, `title`, and `description`.
- Output JSON results.

Notes:

- No API key is required.
- The script uses DuckDuckGo Lite (`https://lite.duckduckgo.com/lite/`) and parses result cards.
- Result count is fixed at 20.

## Run With uv

No external package required (stdlib only):

```bash
uv run <path-to-skill>/scripts/botbot_search.py "latest openai model"
uv run <path-to-skill>/scripts/botbot_search.py "who discovered penicillin"
```

Optional market override:

```bash
uv run <path-to-skill>/scripts/botbot_search.py "what is photosynthesis" --market en-us
```

## Script

- Entrypoint: `scripts/botbot_search.py`
- Replace `<path-to-skill>` with the actual installed skill folder path (for example: `~/.code/skills/botbot-search`).
