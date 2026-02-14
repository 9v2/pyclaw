---
name: tmux
description: Manage tmux sessions, windows, and panes
---

# Tmux Skill

You can manage tmux sessions for the user. Use these patterns:

## Creating Sessions
```bash
tmux new-session -d -s <name>          # create detached session
tmux new-session -d -s <name> -c <dir> # create in specific directory
```

## Managing Windows & Panes
```bash
tmux new-window -t <session>           # new window in session
tmux split-window -h -t <session>      # horizontal split
tmux split-window -v -t <session>      # vertical split
tmux send-keys -t <session> '<cmd>' Enter  # send command to pane
```

## Listing & Attaching
```bash
tmux ls                                # list all sessions
tmux list-windows -t <session>         # list windows
tmux list-panes -t <session>           # list panes
tmux attach -t <session>               # attach to session
```

## Session Control
```bash
tmux kill-session -t <session>         # kill session
tmux kill-server                        # kill all sessions
tmux rename-session -t <old> <new>     # rename session
```

## Capturing Output
```bash
tmux capture-pane -t <session> -p      # print pane contents
tmux capture-pane -t <session> -p -S -100  # last 100 lines
```

When managing long-running processes, prefer creating a dedicated tmux session so the user can monitor and interact with it independently.
