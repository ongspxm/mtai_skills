---
name: botbot-gcal
description: Use when you need to list Google Calendar events in a time range across configured calendars, or add a calendar event to primary calendar via a lightweight JSON-configured CLI.
---

# BotBot Google Calendar

Lightweight Google Calendar helper using a single Python script and JSON config.

## What It Does

- List events between two timestamps (inclusive) across configured calendars.
- Add an event with start/end/title to the primary calendar.
- Refresh Google OAuth access token and persist it to config.
- Refresh Google OAuth access token automatically when expired and persist it to config.

## Config File

Config path resolution order:

1. `--config /path/to/botbot-gcal.json`
2. `$BOTBOT_HOME/botbot-gcal.json`
3. `~/.botbot/botbot-gcal.json`

Example config (`assets/botbot-gcal.example.json`):

```json
{
  "default_timezone": "+8",
  "default_calendars": [
    "primary",
    "work@example.com",
    "Team Calendar"
  ],
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

Notes:

- `default_timezone` controls how input/output timestamps are interpreted/rendered; defaults to `+8` if omitted.
- `default_calendars` entries may be calendar ids (recommended), `primary`, or calendar names.
- For `add`, events are always inserted into the `primary` calendar.
- If `access_token` is expired and `refresh_token` + `client_id` + `client_secret` exist, token refresh is automatic.
- Refreshed token data is written back to the same JSON config file.
- `refresh` verifies required Google Calendar scope (`https://www.googleapis.com/auth/calendar`); if missing, it triggers interactive OAuth re-consent and updates config.
- `ls` prints a workflow-style text list (one event per line), not raw JSON.

## IMPT: Run With uv -- ALWAYS MAKE SURE TO RUN IT WITH UV

No external package required (stdlib only):

```bash
uv run <path-to-skill>/scripts/botbot_gcal.py ls 2026-02-22 2026-02-23
uv run <path-to-skill>/scripts/botbot_gcal.py refresh
uv run <path-to-skill>/scripts/botbot_gcal.py add 2026-02-22T09:00:00Z 2026-02-22T09:30:00Z "Standup"
```

Optional explicit config path:

```bash
uv run <path-to-skill>/scripts/botbot_gcal.py --config ~/.botbot/botbot-gcal.json ls 2026-02-22 2026-02-23
```

## Script

- Entrypoint: `scripts/botbot_gcal.py`
- Replace `<path-to-skill>` with the actual installed skill folder path (for example: `~/.code/skills/botbot-gcal`).
