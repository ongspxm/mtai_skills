---
name: meagent-update-blog
description: Use when you need to trigger and monitor the blog GitLab pipeline to rerender blog content/devlog updates.
---

# MEAGENT-UPDATE-BLOG(1)

## NAME

`meagent-update-blog` - trigger and optionally monitor a GitLab pipeline used to refresh blog content.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/meagent_update_blog.py
```

## DESCRIPTION

This skill mirrors the `update_blog` workflow behavior:
- Trigger pipeline with GitLab pipeline trigger token.
- Poll pipeline status until terminal state by default.
- If polling auth token is missing, still returns the pipeline URL after trigger.

## IMPORTANT

- Always run with `uv run`.
- `token` and `project_id` are required in config.
- `private_token` or `access_token` is recommended for private project polling.
- IMPORTANT: ALWAYS set exec/shell timeout to `10 minutes` because pipeline completion can take a while.

## CONFIG

Config path precedence:
1. `$BOTBOT_HOME/meagent-update-blog.json`
2. `~/.botbot/meagent-update-blog.json`

Example: `assets/meagent-update-blog.example.json`

```json
{
  "url": "https://gitlab.com",
  "project_id": "12345678",
  "token": "pipeline-trigger-token",
  "private_token": "optional-private-token-for-status-polling",
  "ref": "main",
  "poll_interval_seconds": 5,
  "timeout_seconds": 600
}
```

## OUTPUT

The command prints one JSON object:
- `status`: pipeline terminal status, `triggered`, or `timeout`.
- `pipeline_id`: GitLab pipeline id.
- `web_url`: GitLab pipeline page URL.
- `message`: short summary.

## EXAMPLES

```bash
uv run <path-to-skill>/scripts/meagent_update_blog.py
```

## FILES

- Entrypoint: `scripts/meagent_update_blog.py`
- Replace `<path-to-skill>` with your installed skill path (for example `~/.code/skills/meagent-update-blog`).
