---
name: push-public
description: Use when the user wants to publish current work to the public branch as clean commit(s) without exposing main branch history.
---

# PUSH-PUBLIC(1)

## NAME

`push-public` - snapshot `main` onto `public` as clean commit(s).

## SYNOPSIS

```bash
git fetch --all --prune
orig_ref=$(git symbolic-ref --quiet --short HEAD || git rev-parse --short HEAD)
git checkout main
git pull --ff-only origin main
git checkout "$orig_ref"
git worktree add ../public-sync public
cd ../public-sync
git checkout public
git read-tree --reset -u main
git diff --stat
# if the diff is broad, split into a few clean commits by change group
git add -A
git commit -m "<type>: <describe the real changes from git diff>"
git push origin public
cd -
git worktree remove ../public-sync
```

## DESCRIPTION

Keeps `public` history clean: content matches `main`, but commits stay on `public`.

Always do this in a separate worktree rooted on `public` so `main` and your primary working tree are not disturbed.

Before doing any write operations, sync local refs:

```bash
git fetch --all --prune
orig_ref=$(git symbolic-ref --quiet --short HEAD || git rev-parse --short HEAD)
git checkout main
git pull --ff-only origin main
git checkout "$orig_ref"
```

`git read-tree --reset -u main` resets index + working tree to `main`'s tree (tracked files), while leaving `HEAD` on `public`.

When writing commit messages, inspect the diff first (`git diff --stat` and/or `git diff`) and name commits for what actually changed.

Use commit type prefixes (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).

If changes are small and cohesive, use one commit. If changes are huge or mixed across unrelated areas, split into a few clean commits (for example: one for docs, one for skill updates, one for scripts).

## EXAMPLES

```bash
git fetch --all --prune
orig_ref=$(git symbolic-ref --quiet --short HEAD || git rev-parse --short HEAD)
git checkout main
git pull --ff-only origin main
git checkout "$orig_ref"
git worktree add ../public-sync public
cd ../public-sync
git checkout public
git read-tree --reset -u main

# one cohesive change
git add push-public/SKILL.md
git commit -m "docs: update push-public workflow notes"

# second cohesive change when needed
git add AGENTS.md
git commit -m "chore: align push-public commit conventions"

git push origin public
cd -
git worktree remove ../public-sync
```
