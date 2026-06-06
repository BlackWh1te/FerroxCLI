# Conflict resolution skill

## Default heuristic
1. **Type/import wins** — a renamed import or new public function from the
   other agent's branch is harder to re-derive than a local edit. Keep theirs.
2. **Smallest diff wins** — if both branches added ~5 lines to the same region,
   take the union, then re-format with `ruff format`.
3. **Zone owner wins** — for files in the **Shared** list, neither side has
   priority by default. The integrator (user) breaks ties.

## When NOT to auto-resolve
- Both agents renamed the same function to different names → **stop, ask user**.
- Both agents added a new slash command to `cli.py` → fine, but order them
  alphabetically and run `ruff format` to settle the diff.
- A test fails *only* on the merged branch (not on either side alone) →
  **stop**, the contracts diverged. Read both diffs; the test tells you which
  side drifted.

## If the merge is too messy
```bash
# throw away the merge and replay your work on top of fresh main
git merge --abort
git fetch
git rebase origin/main
pytest -q          # still green?
```

If rebasing reintroduces the same conflicts, the branches have diverged too
far for an auto-merge. Escalate to the user.

## When to give up and ask the user
- 3+ files with content conflicts in one merge.
- Public API change on both sides.
- A test fails on the merged result that passed on both sides.
- You can't tell from context which side is "right".

When you escalate, write a `HANDOFF.md` row with the subject
`ESCALATE: <one-line summary>` so it's easy to find.
