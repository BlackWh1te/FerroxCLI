# Merge cadence skill

## Per-session rhythm

```
session start
  ├─ cd ../ferrox-agent-<me>
  ├─ git fetch
  ├─ git merge origin/agent-<other>     # or: git rebase
  ├─ pytest -q                          # must be green
  └─ ruff check ferrox/                 # must be clean (or only pre-existing)

work session
  ├─ claim any shared files first
  ├─ small atomic commits
  ├─ push after each commit:  git push origin agent-<me>
  └─ append handoff row after each commit

session end
  ├─ pytest -q && ruff check ferrox/   # final green
  ├─ git push
  └─ update Active work → idle or blocked
```

## Why merge both directions
- `git fetch` + `merge` keeps both sides aware of each other's renames and API
  changes **before** they conflict with in-flight work.
- Doing it at session start (not end) means if the merge fails, you find out
  with a clean tree — not on top of 2 hours of edits.

## Conflict types and the fix

| Symptom                                                  | Cause                                        | Fix                                                                 |
| -------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------- |
| `CONFLICT (content): Merge conflict in ferrox/cli.py`    | Both edited same region                      | Open file, resolve, `git add`, `git commit`. The integrator wins ties. |
| `CONFLICT (rename/add): ...`                             | One side renamed, other side edited old path | Keep the rename; port the edits to the new path.                    |
| `CONFLICT (modify/delete):`                              | One side deleted a file the other edited     | Generally keep the edit, restore the file.                          |
| Repeated conflicts after resolution                      | Divergent strategies on shared API           | Stop, write a handoff row, sync with the user.                      |

## Green-bar discipline
A branch is "green" only if:
1. `pytest -q` passes
2. `ruff check ferrox/` reports 0 errors
3. `git status` is clean

Do not push a red branch. The other agent's `git merge` will inherit your
failures.
