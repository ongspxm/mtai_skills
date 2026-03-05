---
name: setup-precommit
description: set up pre-commit for a repo
---

# SETUP-PRECOMMIT(1)

## NAME

`setup-precommit` - initialize and configure `pre-commit` hooks for a repository.

## SYNOPSIS

```bash
# run from git root
pipx install pre-commit  # if missing
pre-commit run --all-files
```

## DESCRIPTION

Workflow:
1. Detect git root and run all steps there.
2. Inspect repo languages.
3. Install `pre-commit` with `pipx` if needed.
4. Create/update `.pre-commit-config.yaml`.
5. Validate config by running pre-commit before committing.

## IMPORTANT

- Always include JSON and YAML formatting hooks from `pre-commit-hooks`.
- Never install `codespell`.
- For Python, use only `astral-sh/ruff-pre-commit` with `ruff-check --fix` and `ruff-format`.
- For shell files, use `shellcheck-py/shellcheck-py` and exclude `SC1091`.
- For web files (`html/js/css`), use `biomejs/pre-commit` with version `> v2.1.3` and `biome-check`.
- Add gitignore override for `.pre-commit-config.yaml` so the file is pushed.
- Do not modify `.gitignore` in any other way.

## SOURCES

- `https://pre-commit.com/`
- `https://github.com/pre-commit/pre-commit-hooks/blob/main/.pre-commit-hooks.yaml`
- `https://github.com/astral-sh/ruff-pre-commit`
- `https://github.com/shellcheck-py/shellcheck-py`
- `https://github.com/biomejs/pre-commit`
