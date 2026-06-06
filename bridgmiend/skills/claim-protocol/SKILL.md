# Claim protocol skill

## When to claim
Before editing any file in the **Shared** list in `bridgmiend/AGENTS.md`. Files
in your own zone do not need a claim.

## Steps

1. **Open `bridgmiend/AGENTS.md`.**
2. **Append a row** to the `Claims ledger` table:
   ```
   | B | ferrox/cli.py | 14:32Z | ~20m | no |
   ```
   - `Agent` — your slot letter.
   - `File` — exact repo-relative path.
   - `Claimed at` — UTC, `HH:MMZ` is fine.
   - `ETA` — rough time you'll commit by.
   - `Done?` — `no` initially.
3. **Update** the `Active work` row for your slot:
   - `Status` → `working`
   - `Task` → short description
4. **Commit the board change** in your worktree:
   ```bash
   git add bridgmiend/AGENTS.md
   git commit -m "[agent-a] claim: ferrox/cli.py (refactor /fix dispatch)"
   ```
   This is important — the other agent needs to see your claim when they fetch.
5. **Edit the file.** Stay within the ETA; if you overrun, update the row.
6. **When you commit the work:**
   - Remove the row from `Claims ledger`.
   - Set `Active work` → `done` (or back to `idle` if no follow-up).
   - Append a row to `HANDOFF.md`.

## Conflict — file already claimed

If you open `AGENTS.md` and the file you need is already in the ledger for the
**other** agent:

1. **Do not edit the file.**
2. Set your own `Active work` → `blocked` with a one-line reason.
3. Append a `HANDOFF.md` row explaining what you need and why.
4. Either:
   - wait for them to release (poll the file), or
   - do work in a disjoint zone, or
   - ask the user to designate a winner and edit `AGENTS.md` to reflect it.

## Conflict — you realized you also need a file the other agent has claimed
*after* starting your task:

1. Drop a one-line note in `HANDOFF.md` (`need ferrox/api.py too — see ledger`).
2. Do not touch the file. Wait, or pivot to prep work.
