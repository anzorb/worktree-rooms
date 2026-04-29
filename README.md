# worktree-rooms

[![CI](https://github.com/anzorb/worktree-rooms/actions/workflows/ci.yml/badge.svg)](https://github.com/anzorb/worktree-rooms/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/anzorb/worktree-rooms/branch/main/graph/badge.svg)](https://codecov.io/gh/anzorb/worktree-rooms)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A git worktree manager with a hospital-room metaphor. Assign named "rooms" to parallel workstreams, track PR and CI status, and navigate between them instantly.

```
myproject
  ROOM          BRANCH          LAST COMMIT  STATUS
  ────────────────────────────────────────────────────────
  room-1        —               —            [free]
  room-2        feature/login   45m ago      🔨in-progress  #42 ✅
  room-3        fix/crash       2h ago       🔨in-progress  no PR
  emergency-1   fix/hotfix-99   3h ago       🟣 merged  #38
```

## Requirements

- Python 3.10+
- git
- [gh CLI](https://cli.github.com/) _(optional — needed for PR and CI status in `rooms ls`)_

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/anzorb/worktree-rooms/main/install.sh | bash
```

The installer detects which shells you have configured (zsh, bash, fish) and sets up each one automatically. Then reload your shell:

```bash
source ~/.zshrc          # zsh
source ~/.bashrc         # bash
# fish: open a new terminal, or:
source ~/.config/fish/conf.d/rooms.fish
```

### Manual install

```bash
git clone https://github.com/anzorb/worktree-rooms.git
cd worktree-rooms
cp rooms ~/bin/rooms
chmod +x ~/bin/rooms
```

Then append the config for your shell:

```bash
# zsh
cat shell/rooms.zsh >> ~/.zshrc && source ~/.zshrc

# bash
cat shell/rooms.bash >> ~/.bashrc && source ~/.bashrc

# fish
cp shell/rooms.fish ~/.config/fish/conf.d/rooms.fish
```

Make sure `~/bin` is on your `$PATH`:

```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc   # or ~/.bashrc
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/anzorb/worktree-rooms/main/uninstall.sh | bash
```

## Commands

### `rooms add <path-or-url> <room-name> [branch]`

Register a new room backed by a git worktree.

```bash
# From a local repo
rooms add ~/dev/myproject room-1

# From a GitHub URL (clones to ~/code/myproject first)
rooms add git@github.com:org/myproject.git room-1

# Branch off a specific base branch
rooms add ~/dev/myproject emergency-1 main
```

Rooms are created under `~/rooms/<room-name>` by default. Change `rooms_base` in `~/.config/rooms/config.json` to customise.

---

### `rooms ls`

List all rooms grouped by project, with branch, last commit age, PR number, and CI status.

```
myproject
  ROOM         BRANCH          LAST COMMIT  STATUS
  ───────────────────────────────────────────────────────
  room-1       —               —            [free]
  room-2       feature/login   45m ago      🔨in-progress  #42 ✅
  room-3       fix/crash       2h ago       🔨in-progress  no PR
  emergency-1  —               —            [free]
```

- **[free]** — room is on its placeholder branch, ready to take work
- **🔨in-progress** — room has an active branch
- **🟣 merged** — branch has been merged into the default branch
- PR numbers are **clickable** in OSC 8-capable terminals (iTerm2, Kitty, WezTerm)
- CI emojis: ✅ passing · ❌ failing · 🔄 in progress

Works offline using cached data — shows "offline — cached data from Xh ago" when the remote is unreachable.

---

### `rooms occupy <project/room> [branch]`

Enter a free room and optionally check out a branch. **Changes your shell's working directory** to the room.

```bash
rooms occupy myproject/room-1
rooms occupy myproject/room-1 feature/my-branch
```

Tab completion works for both `project/room` specs and branch names. If there is only one project and the room name is unambiguous, the bare room name is also accepted.

---

### `rooms free <project/room>`

Return a room to its placeholder branch, marking it available for new work.

```bash
rooms free myproject/room-2
```

Refuses to run if the room has uncommitted changes.

---

### `rooms remove <project/room>`

Remove a free room: deletes the worktree directory, removes the placeholder branch, and unregisters the room from config.

```bash
rooms remove myproject/room-1
```

Only free rooms (on their placeholder branch) can be removed. Occupied rooms must be freed first.

---

### `rooms move <project/source-room> <project/target-room>`

Move a branch from one room to another. Target must be free.

```bash
rooms move myproject/room-2 myproject/emergency-1
```

Frees the source first (to release the git branch lock), then checks out in the target. Rolls back if the target checkout fails.

---

### `rooms purge`

Scan for rooms whose branches have been merged or fully pushed to remote, then offer to free them and delete the local branch.

```bash
rooms purge
```

Shows a confirmation prompt (default: No) before making any changes.

---

## Configuration

Config is stored at `~/.config/rooms/config.json`:

```json
{
  "rooms_base": "~/rooms",
  "rooms": [
    {
      "name": "room-1",
      "main_repo": "/Users/you/dev/myproject",
      "path": "/Users/you/rooms/room-1",
      "placeholder_branch": "room-1",
      "default_branch": "main"
    }
  ]
}
```

Change `rooms_base` to any directory you prefer — new rooms will be created there.

### `rooms config set-base-path <path>`

Set the directory where new rooms are created.

```bash
rooms config set-base-path ~/dev/rooms
```

This updates `rooms_base` in `~/.config/rooms/config.json`. Only affects new rooms created with `rooms add` — existing worktrees are not moved.

---

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt pytest-cov

# Run tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=rooms --cov-report=term-missing
```

Tests mock all `git` and `gh` subprocess calls — no real repositories required.
