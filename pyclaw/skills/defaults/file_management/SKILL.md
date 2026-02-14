---
name: file_management
description: Read, write, search, and organize files
---

# File Management Skill

You can work with files on the user's system. Follow these patterns:

## Reading Files
```bash
cat <file>                              # print entire file
head -n 50 <file>                       # first 50 lines
tail -n 50 <file>                       # last 50 lines
tail -f <file>                          # follow file updates
less <file>                             # paginated view
wc -l <file>                            # count lines
```

## Searching
```bash
grep -rn "pattern" <dir>               # recursive search with line numbers
grep -rni "pattern" <dir>              # case-insensitive
find <dir> -name "*.py"                # find files by name
find <dir> -type f -mtime -1           # files modified in last day
fd "pattern"                            # fast find alternative
rg "pattern" <dir>                     # fast grep alternative
```

## Writing & Editing
```bash
echo "content" > <file>                # write (overwrite)
echo "content" >> <file>               # append
tee <file>                              # write from stdin
sed -i 's/old/new/g' <file>            # find and replace
```

## File Operations
```bash
cp <src> <dst>                          # copy
mv <src> <dst>                          # move / rename
rm <file>                               # delete file
rm -rf <dir>                            # delete directory
mkdir -p <path>                         # create directories
chmod +x <file>                         # make executable
```

## Directory Navigation
```bash
ls -la                                  # detailed listing
tree -L 2                               # directory tree
du -sh <dir>                            # directory size
pwd                                     # current directory
```

Always confirm before deleting or overwriting files. Prefer creating backups before destructive operations.
