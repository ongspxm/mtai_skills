---
title: "meagent-daily-logging stage 1 telegram daily text logging"
active: "false"
planned: ""
closed: "2026-03-05"
notes: "Stage 1 only: ingest Telegram text messages into monthly markdown log files and stdout, then generate a user summary."
---

## Problem

Important updates are spread across multiple Telegram groups, making daily review manual and inconsistent.
Stage 1 needs a simple logging-first flow: collect messages into a fixed markdown log format,
print the same log lines to stdout, then provide a summary to the user.

- Priority: High
- Effort: High (> 4 hours)
- Impact: Reliable daily situational awareness with minimal structure and fast implementation.

## Solution

Implement `meagent-daily-logging` as a single script.
All logic stays in one file with low abstraction.
This phase is logging-first and intentionally skips AAR.
Use minimal dependencies: Python stdlib + `telethon` only.

1. Ingest
- Authenticate to Telegram API using a user-scoped Telethon session (`api_id`, `api_hash`, phone/OTP).
- Pull messages from a configured allowlist of groups/channels.
- Restrict ingestion window to `2:00 AM -> next day 2:00 AM` (local timezone aware).
- Keep text-only for stage 1.
- Do not use Telegram bot polling as primary ingestion for stage 1.

2. Log format and storage
- Output is monthly markdown files: `YYYY-MM.md`.
- Within each monthly file, separate days using a level-1 header:
  - `# YYYY-MM-DD`
- Under each day header, store lines sorted by message time (earliest -> latest).
- Each log entry is plain text and starts with the configured chat tag:
  - `(tag) message text`
- No extra headers/metadata per entry in stage 1.
- Rerun/idempotency rule: rewrite the full day section for the target day on each run (do not blindly append), so reruns and edits do not create duplicate lines.
- Normalize multiline message text to a single line before writing.

3. Summarize
- Stage-1 note: this stage first populates the markdown daily log section.
- The same log lines are also printed to stdout.
- After logging, model generates and returns a user-facing summary.

4. AAR
- Not included in stage 1.
- TODO: add AAR features in a later stage.

Runtime/config conventions:
- Default config path: `~/.botbot/meagent-daily-logging.json`
- No `--config` flag in stage 1.
- Telethon session path: `~/.botbot/meagent-daily-logging.session`
- Config includes chat allowlist + shorthand tags, timezone, and a required `log_folder` path where monthly files are written.

Operational notes:
- Treat this as logging, not rich document generation.
- Fail fast on auth/config errors.
- Treat session credentials as secrets and keep local file permissions strict.

## Files to Modify

- `skills/meagent-daily-logging/SKILL.md` (new: skill spec in man-page style)
- `skills/meagent-daily-logging/skill.py` (new: single-file implementation containing full workflow)

## Verification

1. Configure 2-3 Telegram groups with shorthand tags in `~/.botbot/meagent-daily-logging.json` and run sync.
2. Confirm output file for month exists in `YYYY-MM.md` format under configured `log_folder`.
3. Confirm date section header exists as `# YYYY-MM-DD` for the 2am->2am window day.
4. Confirm each entry line is plain text in `(tag) message` format.
5. Confirm entries are sorted earliest to latest within the day section.
6. Confirm the same entries are printed to stdout.
7. Confirm model returns a summary to user after log population.
8. Simulate auth/config failure and verify clear non-zero error.
9. Re-run for the same day and confirm no duplicate line growth in that day section.
10. Edit one Telegram message in-window, rerun, and confirm the day section reflects the latest text.

## Related

- Telegram API / client library docs
- Existing skill/runtime config patterns
