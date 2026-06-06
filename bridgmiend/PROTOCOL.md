# PROTOCOL — rules of engagement

> **Read once at session start. Obey always.** Amendments go at the bottom in the
> `Amendment log`; do not edit the body of the rules.

## 0. Premise

Two AI coding agents work the same FerroxCLI checkout. They are equal peers —
neither is "in charge". The user is the final integrator when both sides want
to touch the same thing.

## 1. Isolation

1. **Worktrees are mandatory.** Each agent edits in its own git worktree
   (`../ferrox-agent-a`, `../ferrox-agent-b`). See
   `skills/worktree/SKILL.md`.
2. **No direct edits on `main`.** All work commits to `agent-a` or `agent-b`.
3. **No edits in the other's worktree.** The file system will let you, but
   don't — that defeats the point.

## 2. Zone discipline

1. **Stay in your zone** (see `AGENTS.md` → `Zones`). Your zone files are yours
   by default — no need to claim.
2. **Claim before editing shared files** (see `AGENTS.md` → `Shared`). Process:
   1. Edit `AGENTS.md` → `Claims ledger` with file, time, ETA.
   2. Only then open the file.
   3. When the commit lands, delete the row and update `Active work`.
3. **If a claim is already in the ledger for a file you need:**
   - Same-agent claim: continue.
   - Other-agent claim: pick a different file, or wait, or do prep work that
     doesn't touch the contested file. Never edit a file another agent has
     claimed.

## 3. Commits

1. **Prefix every commit** with `[agent-a]` or `[agent-b]` so the integrator
   can filter `git log`.
2. **Small, atomic commits.** One logical change per commit. Easier to
   cherry-pick, easier to revert, easier to review.
3. **Push your branch** at the end of every work session so the other agent
   can fetch it.

## 4. Handoff

1. **After every meaningful commit**, append one row to `HANDOFF.md` (newest
   first):
   ```
   ## <UTC timestamp> — [agent-x]
   - task: <one line>
   - commit: <short hash> <subject>
   - files: <comma-separated paths>
   - for the other agent: <what they should know, e.g. "renamed X to Y" or "added Z to shared API">
   ```
2. **Mirror the last 3 rows** in `AGENTS.md` → `Handoff log` for quick scanning.

## 5. Merge cadence

1. **Fetch the other branch at the start of every work session.**
2. **Merge (or rebase) the other branch into yours before pushing** if the
   other branch has moved. Resolve any conflicts here, in your worktree.
3. **Run `pytest -q` and `ruff check ferrox/`** in your worktree after merging.
   Only push if both are green.
4. **Final integration to `main`** is done by the user (or whichever session
   they designate). Don't push to `main` directly.

## 6. Blocked / stuck

If you are blocked on the other agent:

1. Set your row in `Active work` to `blocked`, write a one-line reason in the
   `Task` column.
2. Append a row to `HANDOFF.md` with `for the other agent: <what I need>`.
3. Do not start a new task in a zone that might also touch the contested
   file. Either wait or do work in a completely disjoint zone.

## 7. Emergency stop

If something has clearly gone wrong (mass conflicts, lost context, divergent
branches):

1. Both agents stop committing.
2. User runs `git worktree remove` on the bad worktree.
3. The surviving branch is rebased onto `main`; the lost work is recovered
   from the other branch's last green commit.

---

## Amendment log

(append-only — newest at top; one line each, never edit older rows)

- (none yet)
