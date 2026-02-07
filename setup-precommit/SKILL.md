---
name: setup-precommit
description: set up pre-commit for a repo
---

#### before doing anything
- identify the git root directory, and run all the operations there
- look thru the files in the repo to see which languages are being used.
- use pipx to install pre-commit if needed

#### setup pre-commit hooks
details in this link: https://pre-commit.com/
to check if the pre-commit is valid, ALWAYS run it before commiting the config yaml file

if ".pre-commit-config.yaml" doesnt exist, create one.
visit this pages and add everything that's active
- https://github.com/pre-commit/pre-commit-hooks/blob/main/.pre-commit-hooks.yaml

NEVER install
- codespell

language specific:
- (not exclusive, for those languages not highlighted here, find appropriate alternatives)
- always include pre-commit rules for json and yaml file formats (the one in pre-commit-hooks, nothing else)
- for python, use https://github.com/astral-sh/ruff-pre-commit (ruff-check --fix and ruff-format), nothing else
- for shell files, add https://github.com/shellcheck-py/shellcheck-py (exclude SC1091)
- for web files (html/js/css), use https://github.com/biomejs/pre-commit (> v2.1.3) (biome-check)

#### always make sure your files are pushed to remote
- add gitignore overrides for ".pre-commit-config.yaml"
- DO NOT alter the .gitignore file in any other way (no comments, no extra changes)
