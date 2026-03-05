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

Use this exact sequence, including `raw_output` mode:
1. `rules` with `raw_output=false`.
2. `fetch` with `raw_output=false`.
3. `tag <idx> <action|reading|junk>` with `raw_output=false` for every row you tag.
4. `status` with `raw_output=false` for iterative tagging rounds.
5. if `status` says there are still untagged rows, keep looping:
   run `tag ...` with `raw_output=false`, then `status` with `raw_output=false`.
6. stop the loop only when `status` says `everything is tagged, review these tags`.
7. run `status` once with `raw_output=true` for final verification.
8. if user requests tag changes, run `tag ...` with `raw_output=false`, then `status` with `raw_output=true` again.
9. run `push` only after user confirmation, with `raw_output=false` and `timeout_seconds=300`.
10. after `push`, run `print` with `raw_output=true`.

## COMMANDS

- `fetch` - pull inbox threads via `botbot-gmail`, write `/tmp/tag_gmail.ndjson`, print rows.
- `rules` - print base tagging rules + Google Tasks rules (`email_gps` by default).
- `tag <idx> <action|reading|junk>` - set tag by local queue index.
- `status` - validate tags, clear invalid tags, print only 20 untagged rows per run until fully tagged.
- `push` - apply labels/trash to Gmail, clean queue state, and output JSON counts (`labelled`, `removed`, `labels_removed`).
- `print` - show untagged first, then grouped `action`/`reading`/`junk`.

## IMPORTANT

- Do not format outputs that are already formatted by the script.
- Default policy: when `raw_output` is not explicitly specified for a command, treat it as `raw_output=false`.
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
