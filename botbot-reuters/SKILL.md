---
name: botbot-reuters
description: Use when you need to fetch Reuters headlines from Google News RSS and print them as plain text.
---

# BOTBOT-REUTERS(1)

## NAME

`botbot-reuters` - lightweight Reuters news RSS CLI that prints headlines in plain text.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/botbot_reuters.py [--config /path/to/botbot-reuters.json] [--limit N]
```

## DESCRIPTION

Fetches Reuters stories from this default feed and prints plain-text output:

`https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en`

By default, prints all items available from the feed.

Output format:
- one line per item: `YYYY-MM-DD, Mon, summary`

## CONFIG

Config path precedence:
1. `--config /path/to/botbot-reuters.json`
2. `$BOTBOT_HOME/botbot-reuters.json`
3. `~/.botbot/botbot-reuters.json`

Config is optional. If missing, built-in defaults are used.

Example: `assets/botbot-reuters.example.json`

```json
{
  "feed_url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
  "timeout_seconds": 20
}
```

## EXAMPLES

```bash
uv run <path-to-skill>/scripts/botbot_reuters.py
uv run <path-to-skill>/scripts/botbot_reuters.py --limit 10
uv run <path-to-skill>/scripts/botbot_reuters.py --config ~/.botbot/botbot-reuters.json --limit 5
```

## FILES

- Entrypoint: `scripts/botbot_reuters.py`
- Replace `<path-to-skill>` with your installed skill path (for example `~/.code/skills/botbot-reuters`).
