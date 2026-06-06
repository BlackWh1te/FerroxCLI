# Handoff skill

## Why
The other agent has no live view of your work. The handoff log is how you tell
them "I renamed X, expect a Y in Z" so they don't accidentally re-introduce
the old name or duplicate effort.

## When to write a row
- After every meaningful commit (not every keystroke).
- When you start something that affects shared state.
- When you finish a chunk and are about to switch tasks.
- When you are blocked and need input.

## Format

Append to `bridgmiend/HANDOFF.md`, **newest at the top**, just below the
`---` divider:

```
## 2026-06-06T14:32Z — [agent-a]
- task: extract /fix dispatch into commands/fix.py
- commit: 7a85c1a "extract /fix command into commands/fix.py"
- files: ferrox/cli.py, ferrox/commands/fix.py
- for the other agent: cli.py shrank by ~120 lines; AgentLoop call site
  unchanged (still `await agent_loop.execute_task_with_test_loop(...)`).
  Safe to import the new module in B's UI work.
```

Field rules:
- `task` — one line, imperative.
- `commit` — short hash + subject line. Find with `git log -1 --oneline`.
- `files` — repo-relative paths, comma-separated.
- `for the other agent` — what they need to know to keep going without you.
  Be specific. "I changed things" is useless; "renamed HistoryManager.load
  → read" is useful.

## Mirroring
After writing, also update the `Handoff log` mini-table at the bottom of
`bridgmiend/AGENTS.md` with the latest 3 rows. Keep it short.
