---
name: meagent-tldr-newsletter
description: Use when you need to read TLDR Newsletter items from Gmail, print concise summaries with cleaned links, and optionally trash matching threads.
---

# MEAGENT TLDR NEWSLETTER(1)

## NAME

`meagent tldr newsletter` - fetch TLDR newsletter emails from Gmail, print parsed headline summaries, and optionally trash newsletter threads.

## SYNOPSIS

```bash
uv run <path-to-skill>/scripts/meagent_tldr_newsletter.py read
uv run <path-to-skill>/scripts/meagent_tldr_newsletter.py trash
```

## DESCRIPTION

This skill replicates the TLDR newsletter workflow behavior:
- Scan inbox threads newest-first.
- Keep only messages from `@tldrnewsletter.com`.
- Parse article blocks and `Links:` section.
- Resolve TLDR short links and strip `utm_` params.
- Trim long descriptions to concise single-line snippets.
- Deduplicate using extracted article link key.

## FLOW

1. Run `read` with `raw_output=True` and send output directly to user.
2. Wait for explicit user confirmation: `ok`.
3. Only after `ok`, run `trash`.

`read` stores the exact thread batch to be deleted later.
`trash` deletes only that stored batch (not a fresh inbox scan).

## COMMANDS

- `read` - print parsed newsletter items as plain text blocks.
- `trash` - trash all TLDR newsletter threads currently in inbox and print result JSON.

## IMPORTANT

- Always run with `uv run`.
- This skill depends on `botbot-gmail` being installed in the same skills root.
- `trash` is destructive and cannot be undone from this tool.
- Always run `read` before `trash`.
- For `read`, keep `raw_output=True` and pass output straight to user.

## STATE FILE

- Path: `/tmp/meagent_tldr_newsletter_threads.json`
- Written by: `read`
- Consumed and deleted by: `trash`

## EXAMPLES

```bash
uv run <path-to-skill>/scripts/meagent_tldr_newsletter.py read
uv run <path-to-skill>/scripts/meagent_tldr_newsletter.py trash
```

## FILES

- Entrypoint: `scripts/meagent_tldr_newsletter.py`
- Replace `<path-to-skill>` with your installed skill path (for example `~/.code/skills/meagent-tldr-newsletter`).
