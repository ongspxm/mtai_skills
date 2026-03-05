---
name: merge-worktree
description: Merge or cherry-pick a worktree branch back into the repo root using a single renderer script.
---

# MERGE-WORKTREE(1)

## NAME

`merge-worktree` - merge or cherry-pick worktree changes back into repo root using rendered instructions.

## SYNOPSIS

```bash
bash <path-to-skill>/render-instructions.sh
```

## DESCRIPTION

Use when a worktree branch must be integrated into the default branch at repo root.

Workflow:
1. Render instructions via `render-instructions.sh`.
2. Execute commands in order.
3. Use `git -C <worktree_path>` for worktree operations.
4. Resolve conflicts line-by-line using `apply_patch` only.
5. Confirm clean `git status`.
6. Remove the worktree shown in instructions (never the repo root).

## IMPORTANT

- Follow rendered steps exactly.
- Do not skip the final cleanup of the target worktree.

## FILES

- Helper script: `render-instructions.sh`
