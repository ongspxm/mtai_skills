---
name: botbot-gcal
description: Use when you need to list Google Calendar events in a time range across configured calendars, or add a calendar event to primary calendar via a lightweight JSON-configured CLI.
---

# BOTBOT-GCAL(1)

## NAME

`botbot-gcal` - lightweight Google Calendar CLI for listing events, adding events, and token refresh.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/botbot_gcal.py [--config /path/to/botbot-gcal.json] <command> [args]
```

## DESCRIPTION

Supports:
- `ls <start> <end>` (inclusive range across configured calendars) - ALWAYS run with raw_output=True
- `add <start> <end> <title>` (always inserts into `primary` calendar)
- `refresh` (refresh token and validate required scope)

## IMPORTANT

- Always run with `uv run`.
- `ls` returns workflow-style text lines, not raw JSON.
- `default_timezone` controls input/output timestamp interpretation and rendering.
- `default_calendars` can contain calendar ids (recommended), `primary`, or calendar names.
- Expired `access_token` auto-refreshes when `refresh_token`, `client_id`, and `client_secret` are present.
- Refreshed token data is persisted back to the same config JSON.
- `refresh` checks scope `https://www.googleapis.com/auth/calendar` and can trigger interactive OAuth re-consent.

## CONFIG

Config path precedence:
1. `--config /path/to/botbot-gcal.json`
2. `$BOTBOT_HOME/botbot-gcal.json`
3. `~/.botbot/botbot-gcal.json`

Example: `assets/botbot-gcal.example.json`

```json
{
  "default_timezone": "+8",
  "default_calendars": ["primary", "work@example.com", "Team Calendar"],
  "api": {
    "base_url": "https://www.googleapis.com/calendar/v3",
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
uv run <path-to-skill>/scripts/botbot_gcal.py ls 2026-02-22 2026-02-23
uv run <path-to-skill>/scripts/botbot_gcal.py add 2026-02-22T09:00:00Z 2026-02-22T09:30:00Z "Standup"
uv run <path-to-skill>/scripts/botbot_gcal.py refresh
uv run <path-to-skill>/scripts/botbot_gcal.py --config ~/.botbot/botbot-gcal.json ls 2026-02-22 2026-02-23
```

## FILES

- Entrypoint: `scripts/botbot_gcal.py`
- Replace `<path-to-skill>` with your installed skill path (for example `~/.code/skills/botbot-gcal`).
