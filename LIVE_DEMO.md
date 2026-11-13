# Live two-Codex demo

This is a local presentation bridge: two real Codex CLI sessions edit two files, and AgentSync observes those filesystem writes in real time. It is deliberately a focused demo of the referee workflow, not an autonomous multi-agent deployment.

## Start the dashboard and live bridge

```bash
pnpm live:setup
pnpm live
```

Open `http://localhost:3000/team/hackathon`.

## Start the two real workers

In two more terminals, open Codex in each folder printed by `pnpm live:setup`.

Auth worker prompt:

```text
In src/user.ts, change user_id from number to string UUID. Preserve valid TypeScript.
```

Profile worker prompt (only after the dashboard reports the conflict):

```text
In src/profile.ts, update every user_id type from number to string UUID. Preserve valid TypeScript.
```

The first real write produces a semantic collision; the second produces the accepted contract and verification events. Do not claim that the bridge identifies which model made a write: it truthfully observes the two designated workspaces and maps them to their running worker roles.
