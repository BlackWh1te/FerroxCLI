# bridgmiend

Coordination layer for two AI coding agents working on the same FerroxCLI checkout.

## What this is

`bridgmiend/` is the **shared brain** between two parallel AI sessions. It contains
all the protocol, status, and skill files they need to coexist on one repo without
clobbering each other.

## Layout

```
bridgmiend/
├── README.md           # you are here
├── AGENTS.md           # LIVE board: zones, active work, claim table
├── PROTOCOL.md         # the rules of engagement (read once, obey always)
├── HANDOFF.md          # append-only log; newest entries at the top
└── skills/             # modular skills both agents load at session start
    ├── worktree/SKILL.md
    ├── claim-protocol/SKILL.md
    ├── handoff/SKILL.md
    ├── merge-cadence/SKILL.md
    └── conflict-resolution/SKILL.md
```

## How the two agents use it

1. **Session start** — both agents read `PROTOCOL.md` and the `Active work` table
   in `AGENTS.md`. Each agent picks a free task or waits.
2. **During work** — agents work in their own git worktree (see
   `skills/worktree/SKILL.md`). The `Active work` table is the single source of
   truth for who is doing what.
3. **Touching shared files** — claim first (see `skills/claim-protocol/SKILL.md`),
   edit, commit, release.
4. **Finishing a chunk** — append a row to `HANDOFF.md` so the other agent has
   context.
5. **Periodic merge** — see `skills/merge-cadence/SKILL.md`.

## Identity

| Slot  | Name          | Branch      | Worktree                       |
| ----- | ------------- | ----------- | ------------------------------ |
| A     | this session  | `agent-a`   | `../ferrox-agent-a`            |
| B     | other session | `agent-b`   | `../ferrox-agent-b`            |

(Adjust the `Identity` table in `AGENTS.md` to match your real setup.)
