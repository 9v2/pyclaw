---
name: shell
description: Execute shell commands and scripts
---

# Shell Skill

You can execute shell commands on the user's system. Follow these guidelines:

## Running Commands
```bash
command                                 # run a command
command arg1 arg2                       # with arguments
command1 | command2                     # pipe output
command1 && command2                    # chain commands
command > output.txt 2>&1              # redirect all output
```

## Process Management
```bash
ps aux | grep <name>                   # find process
kill <pid>                              # stop process
kill -9 <pid>                           # force kill
nohup command &                         # run in background
jobs                                    # list background jobs
```

## System Info
```bash
uname -a                                # system info
df -h                                   # disk usage
free -h                                 # memory usage
top -bn1 | head -20                    # process snapshot
whoami                                  # current user
```

## Package Management
```bash
pip install <package>                   # install python package
pip list                                # list installed packages
apt list --installed                    # list system packages (debian)
```

## Environment
```bash
echo $VARIABLE                          # print env variable
export VAR=value                        # set env variable
env                                     # list all env variables
which <command>                         # find command location
```

Always explain what a command does before running it if it could have side effects. Prefer non-destructive commands and ask before running anything that modifies system state.
