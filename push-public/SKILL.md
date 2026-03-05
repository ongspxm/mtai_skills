---
name: push-public
description: Use when the user wants to publish current work to the public branch as one clean commit without exposing main branch history.
---

# PUSH-PUBLIC(1)

## NAME

`push-public` - snapshot `main` onto `public` as one commit.

## SYNOPSIS

```bash
ORIG_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git fetch --all --prune
git checkout main
git pull --ff-only origin main
git checkout public
git read-tree --reset -u main
git diff --stat
# choose a commit message based on the actual diff
git add -A
git commit -m "<describe the real changes from git diff; if varied, list key changes>"
git push origin public
git checkout "$ORIG_BRANCH"
```

## DESCRIPTION

Keeps `public` history clean: content matches `main`, but commits stay on `public`.

Before switching branches, record the current branch and return to it after push:

```bash
ORIG_BRANCH=$(git rev-parse --abbrev-ref HEAD)
# ... sync public ...
git checkout "$ORIG_BRANCH"
```

`git read-tree --reset -u main` resets index + working tree to `main`'s tree (tracked files), while leaving `HEAD` on `public`.

When writing the commit message, inspect the diff first (`git diff --stat` and/or `git diff`) and name the commit for what actually changed. Avoid generic messages like "sync" when the diff has a clear theme. If changes are broad across unrelated areas, use a concise list-style message that names the main change groups.

## EXAMPLES

```bash
git checkout public
git read-tree --reset -u main
git add -A
git commit -m "chore: sync public branch with main"
git push origin public
```
