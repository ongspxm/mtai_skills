---
name: setup-justevery
description: Configure Code bell notifications, tmux bell visuals, and ensure `CODEX_HOME` is exported in `~/.bashrc` for skill installs.
---

# SETUP-JUSTEVERY(1)

## NAME

`setup-justevery` - set terminal bell notifications for Code and tmux.

## SYNOPSIS

```toml
# ~/.code/config.toml
notify = ["bash", "-c", "printf '\\a'"]
```

```tmux
# ~/.tmux.conf
set-w -g monitor-bell on
set -g bell-action any
set -g window-status-bell-style fg=white,bg=red,bright
```

## DESCRIPTION

Apply this workflow:
1. Ensure `~/.code/config.toml` has exactly:
   `notify = ["bash", "-c", "printf '\\a'"]`
2. If another `notify` value exists, replace it with the value above.
3. Ensure `~/.bashrc` contains:

```bash
# For install skills
export CODEX_HOME=~/.code
```

   If an `export CODEX_HOME=...` line already exists, keep a single correct line and do not duplicate it.
4. Ensure `~/.tmux.conf` contains:

```tmux
# Monitor for the bell signal in all windows
# Trigger the bell action for any window, even if not focused
# reverses the colors of the tab when bell-style
set-w -g monitor-bell on
set -g bell-action any
set -g window-status-bell-style fg=white,bg=red,bright
```

5. If inside a tmux session (`$TMUX` is set), reload tmux config:

```
tmux source-file ~/.tmux.conf
```
