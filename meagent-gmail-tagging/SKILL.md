---
name: meagent-gmail-tagging
description: Use when you need a staged Gmail triage flow (fetch, rules, tag, status, push) that stores a local NDJSON queue before applying labels/trash actions.
---

# MEAGENT-GMAIL-TAGGING(1)

## NAME

`meagent-gmail-tagging` - staged Gmail triage flow with local queueing before label/trash apply.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py <command> [args]
```

## DESCRIPTION

Use this sequence:
1. `rules`
2. `fetch`
3. `tag <idx> <action|reading|junk>` for every row (auto run)
4. `status` returns at most 20 untagged emails each time, with a header like `19 emails untagged, here is 19 of them.`
5. after those rows, it prints guidance like `this is 20/40 untagged email. pick the best tag for each and autotag them, call status with raw_output=false to get more after thats done`.
6. keep running `status` and tagging emails with `raw_output=false`.
7. stop only when `status` says `everything is tagged, review these tags`.
8. only then run `status` one more time with `raw_output=true` for final verification output.
9. adjust tags if user requests changes
10. `push` only after user confirms; run it with `timeout_seconds=300`; it returns JSON counts only.
11. after `push`, run `print` with raw_output=True.

## COMMANDS

- `fetch` - pull inbox threads via `botbot-gmail`, write `/tmp/tag_gmail.ndjson`, print rows.
- `rules` - print base tagging rules + Google Tasks rules (`email_gps` by default).
- `tag <idx> <action|reading|junk>` - set tag by local queue index.
- `status` - validate tags, clear invalid tags, print only 20 untagged rows per run until fully tagged.
- `push` - apply labels/trash to Gmail, clean queue state, and output JSON counts (`labelled`, `removed`, `labels_removed`).
- `print` - show untagged first, then grouped `action`/`reading`/`junk`.

## IMPORTANT

- Do not format outputs that are already formatted by the script.
- For final verification `status`, use raw_output=True.
- Run `push` with raw_output=false.
- For every iterative `status` run during tagging, use raw_output=false.
- After `push`, run `print` with raw_output=true.
- Run `push` with `timeout_seconds=300`.
- `idx` is local queue id, not Gmail `threadid`.
- Keep `threadid` hidden from user-facing output.

## QUEUE FILE

- Path: `/tmp/tag_gmail.ndjson`
- Row schema: `{idx, subject, from, snippet, threadid, tag}`

## DEPENDENCIES

Expected scripts:
- `botbot-gmail/scripts/botbot_gmail.py`
- `botbot-gtask/scripts/botbot_gtask.py`

Resolution base: main skills directory via current skill path (`../../`).
If missing, command fails with a clear "not installed" error.

## EXAMPLES

```bash
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py fetch
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py rules
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py tag 4 action
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py status
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py push
uv run <path-to-skill>/scripts/meagent_gmail_tagging.py print
```
