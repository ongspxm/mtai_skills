---
name: botbot-gtask
description: Use when you need to list Google Task lists, list tasks in a specific list, or add a task (whitelist enforced) via a lightweight JSON-configured CLI.
---

# BotBot Google Tasks

Lightweight Google Tasks helper using a single Python script and JSON config.

## What It Does

- List all Google Task lists.
- Refresh Google OAuth access token and persist it to config.
- List all tasks in a given task list (by title or id).
- Add a task with title + description to a given task list.
- Add a task with title + description; if list is omitted, default to the first list from `ls`.
- Always enforce `edit_whitelist` before adding tasks.

## Config File

Config path resolution order:

1. `--config /path/to/botbot-gtask.json`
2. `$BOTBOT_HOME/botbot-gtask.json`
3. `~/.botbot/botbot-gtask.json`

Example config (`assets/botbot-gtask.example.json`):

```json
{
  "edit_whitelist": [
    "Personal",
    "work-list-id"
  ],
  "api": {
    "base_url": "https://tasks.googleapis.com/tasks/v1",
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

- If `access_token` is expired and `refresh_token` + `client_id` + `client_secret` exist, token refresh is automatic.
- Refreshed token data is written back to the same JSON config file.

## Run With uv

No external package required (stdlib only):

```bash
uv run <skill-path>/scripts/botbot_gtask.py ls
uv run <skill-path>/scripts/botbot_gtask.py refresh
uv run <skill-path>/scripts/botbot_gtask.py tasks --list "Personal"
uv run <skill-path>/scripts/botbot_gtask.py add --list "Personal" --title "Buy milk" --description "2 liters"
uv run <skill-path>/scripts/botbot_gtask.py add --title "Buy milk" --description "2 liters"
```

Optional explicit config path:

```bash
uv run <skill-path>/scripts/botbot_gtask.py --config ~/.botbot/botbot-gtask.json ls
```

## Script

- Entrypoint: `scripts/botbot_gtask.py`
- Replace `<skill-path>` with the actual installed skill folder path (for example: `~/.code/skills/botbot-gtask` or repo-local `botbot-gtask`).
