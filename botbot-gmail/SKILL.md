---
name: botbot-gmail
description: Use when you need to list Gmail threads by query, delete (trash) a thread, or add a label to a thread via a lightweight JSON-configured CLI.
---

# BOTBOT-GMAIL(1)

## NAME

`botbot-gmail` - lightweight Gmail CLI for listing, reading, tagging, trashing threads, and token refresh.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/botbot_gmail.py [--config /path/to/botbot-gmail.json] <command> [args]
```

## DESCRIPTION

Supports:
- `ls [query]` (NDJSON: `{threadid, from, subject, snippet, labels}`; default query `in:INBOX`)
- `read <thread_id>` (latest plaintext body)
- `del <thread_id>` (Gmail `threads.trash`)
- `tag <thread_id> <label>` (label name or id must already exist)
- `refresh` (refresh token and validate required scope)

## IMPORTANT

- Always run with `uv run`.
- OAuth scope required: `https://www.googleapis.com/auth/gmail.modify`.
- Expired `access_token` auto-refreshes when `refresh_token`, `client_id`, and `client_secret` are present.
- Refreshed token data is persisted back to the same config JSON.
- `refresh` can trigger interactive OAuth re-consent if scope is missing.

## CONFIG

Config path precedence:
1. `--config /path/to/botbot-gmail.json`
2. `$BOTBOT_HOME/botbot-gmail.json`
3. `~/.botbot/botbot-gmail.json`

Example: `assets/botbot-gmail.example.json`

```json
{
  "api": {
    "base_url": "https://gmail.googleapis.com/gmail/v1",
    "token_url": "https://oauth2.googleapis.com/token"
  },
  "tokens": {
    "access_token": "ya29...",
    "refresh_token": "1//...",
    "client_id": "...apps.googleusercontent.com",
    "client_secret": "...",
    "expiry": "2026-02-22T10:00:00Z"
  }
}
```

## EXAMPLES

```bash
uv run <path-to-skill>/scripts/botbot_gmail.py ls
uv run <path-to-skill>/scripts/botbot_gmail.py ls "from:alerts@example.com newer_than:7d"
uv run <path-to-skill>/scripts/botbot_gmail.py read 18f9abc123def456
uv run <path-to-skill>/scripts/botbot_gmail.py del 18f9abc123def456
uv run <path-to-skill>/scripts/botbot_gmail.py tag 18f9abc123def456 IMPORTANT
uv run <path-to-skill>/scripts/botbot_gmail.py refresh
uv run <path-to-skill>/scripts/botbot_gmail.py --config ~/.botbot/botbot-gmail.json ls
```

## FILES

- Entrypoint: `scripts/botbot_gmail.py`
- Replace `<path-to-skill>` with your installed skill path (for example `~/.code/skills/botbot-gmail`).
