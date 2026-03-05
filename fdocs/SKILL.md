---
name: fdocs
description: Use for fdocs commands (`init`, `new`, `status`, `close`, `explore`) and workflow-only subcommands (`deep`, `verify`) to run a Feature Docs workflow in a repo.
---

# FDOCS(1)

## SUBCOMMANDS

- Script-backed: `init`, `new`, `status`, `close`, `explore`
- Workflow-only (skill instructions): `deep`, `verify`

## NAME

`fdocs` - bootstrap and maintain a lightweight Feature Docs workflow.

## SYNOPSIS

Always run in a git repo.

```bash
uv run <path-to-skill>/scripts/fdocs.py init
uv run <path-to-skill>/scripts/fdocs.py new "your title"
uv run <path-to-skill>/scripts/fdocs.py status
uv run <path-to-skill>/scripts/fdocs.py status --grooming
uv run <path-to-skill>/scripts/fdocs.py close fd001 --notes "done"
uv run <path-to-skill>/scripts/fdocs.py explore
```

## DESCRIPTION

Core conventions:

- FD files: `docs/fdocs/fdXXX_title.md`
- Numbering: derive from existing FD files (not from index rows)
- Source of truth: FD files are canonical; index is derived output
- Archive path: `docs/fdocs/archive/`
- Index path: `docs/fdocs/_INDEX.md`
- Template path: `docs/fdocs/_TEMPLATE.md`
- FD frontmatter fields: `title`, `active`, `planned`, `closed`, `notes`
- Date format: `planned` and `closed` use `YYYY-MM-DD`
- Final status derivation:
  - `closed` set -> `closed`
  - else `planned` set -> `planned`
  - else `active=true` -> `open`
  - else (`active=false` or missing) -> `backlog` (default)
- Optional changelog support via `CHANGELOG.md` using Keep a Changelog format
- Optional engineering-rules support via `docs/dev_guide/*.md`

## CMDS

### fdocs init

- Purpose: initialize `docs/fdocs` scaffolding in a repo.
- cmd: `uv run <path-to-skill>/scripts/fdocs.py init`
- Create:
  - `docs/fdocs/_TEMPLATE.md` from `templates/_TEMPLATE.md`
  - `docs/fdocs/archive/`
  - `docs/fdocs/_INDEX.md` (via status generation)
- Optional:
  - create `CHANGELOG.md` from `templates/CHANGELOG.md`
  - create `docs/dev_guide/*.md` from `templates/dev_guide/*.md`
  - append FD guidance block to `AGENTS.md` from `templates/AGENTS_MD_ADDITIONAL.md` (idempotent)

### fdocs new

- Purpose: create next numbered fdoc from template.
- cmd: `uv run <path-to-skill>/scripts/fdocs.py new "Title"`
- Output: `fdoc created: docs/fdocs/fdXXX_....md`
- After create, fill:
  - frontmatter: `active`, `planned`, `closed`, `notes`
  - sections: `Problem`, `Solution`, `Files to Modify`, `Verification`, `Related`

### fdocs status

- Purpose: regenerate index and print active table.
- cmd: `uv run <path-to-skill>/scripts/fdocs.py status`
- Fast path: `status`
  - use when state is known fresh.
- With grooming: `status --grooming`
  - cmd: `uv run <path-to-skill>/scripts/fdocs.py status --grooming`
  - use when state is uncertain.
  - housekeeping moves closed docs from `docs/fdocs/` to `docs/fdocs/archive/`

### fdocs close

- Purpose: mark fdoc closed and archive it.
- cmd: `uv run <path-to-skill>/scripts/fdocs.py close <fd> [--notes ...] [--date YYYY-MM-DD]`
- Behavior:
  - set `active=false`, `planned=""`, `closed=<date>`
  - update `notes` when provided
  - move file to `docs/fdocs/archive/`
  - regenerate `docs/fdocs/_INDEX.md`

### fdocs explore

- Purpose: project and fdoc context exploration.
- first run the cmd: `uv run <path-to-skill>/scripts/fdocs.py explore`
  - `Fdocs Status` (active table + counts)
  - `Recent Activity` (branch, recent commits, files in recent commits, uncommitted changes)
  - `Quick Reference` table
- Project overview (do these):
  - Read `AGENTS.md` and `README.md` first.
  - Read other top-level docs if present (for example `docs/*.md`, `CONTRIBUTING.md`).
  - Inspect top-level repo structure to understand key directories.
  - Infer tech stack from root config files (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Makefile`).
  - Call out non-obvious constraints/gotchas from `AGENTS.md`.
- Summarize everything from project overview + fdocs status + recent activity + quick reference

### fdocs deep

- Purpose: deep multi-angle analysis workflow.
- Status: skill instruction only (not implemented in script).
- Use this workflow:
  - Phase 1: Understand the problem
    - Parse the problem statement and clarify what outcome is needed.
    - Gather quick context from recent conversation/work.
    - If a relevant active fdoc exists, read it first.
    - Do a brief targeted scan of the code area to seed exploration.
  - Phase 2: Design 4 exploration angles
    - Pick 4 distinct lenses (non-overlapping) for the same problem.
    - Check orthogonality: if two angles are too similar, reframe one.
    - For each angle define:
      - starting files/search patterns
      - specific question to answer
      - depth vs breadth target
  - Phase 3: Launch parallel exploration
    - Tell user the 4 angles briefly, then launch immediately.
    - Spawn 4 parallel sub-agents (read-only) with explicit angle prompts.
    - Require evidence-backed findings with concrete file references.
  - Phase 4: Verify key claims
    - Pass 1: contradiction detection across agent outputs.
    - Pass 2: factual verification of the most decision-critical claims.
    - Prioritize claims that would change the recommendation if wrong.
  - Phase 5: Synthesize
    - Produce one merged analysis with these sections:
      - Agreements
      - Tensions
      - Surprises
      - Corrections
      - Recommendation
      - Assumption check
    - Recommendation should include approach, tradeoffs, risks, assumptions, and first step.
  - Phase 6: Fdoc follow-up (if applicable)
    - If an active fdoc is relevant, propose concrete updates to its `## Solution` section.
    - Do not auto-edit the fdoc; present suggested edits for approval.
- Notes:
  - Always use 4 angles.
  - Keep agents independent (no cross-anchoring).
  - Prefer fast, high-signal synthesis over over-polished output.

### fdocs verify

- Purpose: post-implementation verification workflow.
- Status: skill instruction only (not implemented in script).
- Use this workflow:
  - Phase 1: Commit check (no approval needed)
    - Run `git status` and `git diff` to inspect pending changes.
    - If there are implementation-related uncommitted changes, stage and commit with a concise message.
    - If nothing to commit, state that clearly and continue.
  - Phase 2: Proofread pass (no approval needed)
    - Review all changed files for correctness (logic/edge cases), consistency (naming/patterns), completeness (all paths covered), and cleanliness (no debug leftovers).
    - If issues are found, fix them and commit those fixes separately with a clear message.
    - If clean, state that the code looks good.
  - Phase 3: Verification plan (requires approval)
    - Propose a concrete numbered plan covering local checks, integration/manual checks, edge cases, and expected success signals.
    - Present the plan and wait for approval before running tests.
    - After approval, append the finalized plan to the relevant fdoc under `## Verification` (or update that section if it already exists).
  - Phase 4: Execute (after approval)
    - Run approved steps in order and report pass/fail per step with concise notes.
