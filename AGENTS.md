# AGENTS

## Design Notes

- For any `botbot-xxx` skill, the default runtime config file location must be under `~/.botbot`.
- Follow the existing convention: `~/.botbot/<skill-name>.json` (for example, `~/.botbot/botbot-gcal.json`).
- If a `--config` flag is provided, that explicit path still takes precedence.
