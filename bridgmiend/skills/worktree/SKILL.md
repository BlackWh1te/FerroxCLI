# Worktree skill

## Purpose
Give each agent a physically separate working directory so they can never
overwrite each other's in-flight edits.

## One-time setup
Run from the **main** FerroxCLI checkout (do not run inside an existing
worktree):

```bash
# from FerroxCLI/
git worktree add ../ferrox-agent-a -b agent-a main
git worktree add ../ferrox-agent-b -b agent-b main
```

Verify:

```bash
git worktree list
# expected:
# C:/.../FerroxCLI            7a85c16 [main]
# C:/.../ferrox-agent-a       7a85c16 [agent-a]
# C:/.../ferrox-agent-b       7a85c16 [agent-b]
```

## Per-session

Point each opencode/Claude session at its own worktree:

- Agent A → `C:/.../ferrox-agent-a`
- Agent B → `C:/.../ferrox-agent-b`

The session's `CLAUDE.md`, `.env`, `bridgmiend/` content is **shared** via git
(it is the same on all branches), so changes to the board/protocol propagate
naturally when you commit and the other side pulls.

## Branch hygiene

```bash
# at session start
cd ../ferrox-agent-a        # or -b
git fetch
git merge origin/agent-b    # bring the other side's work into yours
pytest -q && ruff check ferrox/   # must be green before you push
```

## Teardown

When you're done with multi-agent mode:

```bash
git worktree remove ../ferrox-agent-a
git worktree remove ../ferrox-agent-b
git branch -d agent-a agent-b   # only if merged into main
```
