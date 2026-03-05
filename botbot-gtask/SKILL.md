---
name: botbot-gtask
description: Use when you need to list Google Task lists, list tasks in a specific list, or add a task (whitelist enforced) via a lightweight JSON-configured CLI.
---

# BOTBOT-GTASK(1)

## NAME

`botbot-gtask` - lightweight Google Tasks CLI for listing task lists, listing tasks, adding tasks, and token refresh.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/botbot_gtask.py [--config /path/to/botbot-gtask.json] <command> [args]
```

## DESCRIPTION

Supports:
- `ls` (list task lists)
- `tasks --list <title-or-id>` (list tasks in a task list)
- `add --title <title> --notes <notes> [--list <title-or-id>]` (create task)
- `refresh` (refresh token and validate required scopes)

If `--list` is omitted for `add`, the first list from `ls` is used.

## IMPORTANT

- Always run with `uv run`.
- `add` is always gated by `edit_whitelist`.
- OAuth scopes checked by `refresh`:
  `https://www.googleapis.com/auth/tasks` and
  `https://www.googleapis.com/auth/tasks.readonly`.
- Expired `access_token` auto-refreshes when `refresh_token`, `client_id`, and `client_secret` are present.
- Refreshed token data is persisted back to the same config JSON.
- `refresh` can trigger interactive OAuth re-consent if required scopes are missing.

## CONFIG

Config path precedence:
1. `--config /path/to/botbot-gtask.json`
2. `$BOTBOT_HOME/botbot-gtask.json`
3. `~/.botbot/botbot-gtask.json`

Example: `assets/botbot-gtask.example.json`

```json
{
  "edit_whitelist": ["Personal", "work-list-id"],
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

## EXAMPLES

```bash
uv run <path-to-skill>/scripts/botbot_gtask.py ls
uv run <path-to-skill>/scripts/botbot_gtask.py tasks --list "Personal"
uv run <path-to-skill>/scripts/botbot_gtask.py add --list "Personal" --title "Buy milk" --notes "2 liters"
uv run <path-to-skill>/scripts/botbot_gtask.py add --title "Buy milk" --notes "2 liters"
uv run <path-to-skill>/scripts/botbot_gtask.py refresh
uv run <path-to-skill>/scripts/botbot_gtask.py --config ~/.botbot/botbot-gtask.json ls
```

## FILES

- Entrypoint: `scripts/botbot_gtask.py`
- Replace `<path-to-skill>` with your installed skill path (for example `~/.code/skills/botbot-gtask`).
