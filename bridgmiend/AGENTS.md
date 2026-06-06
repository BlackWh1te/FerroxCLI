# Agents — Live Coordination Board

> **MUTABLE** — both agents edit this file. Keep entries short. Append-only for
> the `Handoff log` section.

## Identity

| Slot | Role          | Branch      | Worktree                       | Session label prefix |
| ---- | ------------- | ----------- | ------------------------------ | -------------------- |
| A    | this session  | `agent-a`   | `../ferrox-agent-a`            | `[agent-a]`          |
| B    | other session | `agent-b`   | `../ferrox-agent-b`            | `[agent-b]`          |

## Zones (do not edit outside your zone without claiming first)

| Zone                           | Owner | Notes                                 |
| ------------------------------ | ----- | ------------------------------------- |
| `ferrox/agent/`                | A     | orchestrator, tools, agent pool       |
| `ferrox/providers/`            | A     | provider registry, config             |
| `tests/test_agent/`            | A     |                                       |
| `ferrox/ui/`                   | B     | trace viewer, progress, notifications |
| `ferrox/utils/`                | B     | indexer, memory, history, content gen |
| `tests/test_ui/`, `tests/test_utils/` | B |                                       |
| `docs/`                        | B     | docs/, *.md guides                    |
| **Shared — claim before edit** | both  | see list below                        |

### Shared (claim before editing)

`ferrox/cli.py` · `ferrox/config.py` · `ferrox/api.py` · `ferrox/permissions.py` ·
`ferrox/modes.py` · `ferrox/tools.py` · `ferrox/exceptions.py` ·
`ferrox/fallback.py` · `pyproject.toml` · `pytest.ini` · `ruff.toml` · `.mypy.ini` ·
`tests/conftest.py` · `CLAUDE.md` · `bridgmiend/PROTOCOL.md`

## Active work

<!-- Edit the row for your slot when you start, commit, or finish. -->

| Agent | Status   | Branch   | Task                                                | Last commit | Claimed files |
| ----- | -------- | -------- | --------------------------------------------------- | ----------- | ------------- |
| A     | `idle`   | `agent-a` | —                                                 | —           | —             |
| B     | `idle`   | `agent-b` | —                                                 | —           | —             |

**Status values:** `idle` · `working` · `blocked` · `merging` · `done`

## Handoff log

(Mirror of the top entries from `HANDOFF.md` — keep just the last 3 here for
quick scanning.)

| When (UTC) | Agent | What changed                                          | Commit    |
| ---------- | ----- | ----------------------------------------------------- | --------- |
| —          | —     | (none yet)                                            | —         |

## Claims ledger (transient)

<!-- Drop a row when you claim a shared file; delete the row when you commit. -->

| Agent | File               | Claimed at | ETA       | Done? |
| ----- | ------------------ | ---------- | --------- | ----- |
| —     | —                  | —          | —         | —     |
