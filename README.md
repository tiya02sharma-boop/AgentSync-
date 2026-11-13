# AgentSync

AgentSync is a coordination layer for teams using multiple coding agents. It makes task ownership
and shared code resources visible, flags incompatible interface changes, and gives people a chance
to approve a proposed contract before it is marked verified.

This repository contains a FastAPI coordination API, a Next.js activity dashboard, and the
Agentigram agent-coordination runtime and simulator. The API is an MVP; the dashboard currently
shows its own simulator-backed room and is not yet wired to the FastAPI API.

## What it does

- Registers tasks with the files and symbols each agent plans to change.
- Reserves declared resources and rejects conflicting reservations.
- Receives Nonilion webhook events at `POST /webhook/nonilion`.
- Detects an API contract conflict when an interface changes while another task consumes that
  symbol.
- Records a proposed resolution and requires human approval before verification.

Conflict detection is deterministic and does not depend on an LLM.

## Run the API locally

Requires Python 3.11 or newer.

```bash
cd apps/agentsync-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the interactive API, or check <http://localhost:8000/health>.

## Run the dashboard locally

Requires Node.js 22 or newer and pnpm 10.34.5. From the repository root:

```bash
corepack enable
pnpm install
pnpm dev
```

Open <http://localhost:3000/team/hackathon>. This view uses the included simulator. To test the
two-agent local demo, follow [LIVE_DEMO.md](LIVE_DEMO.md).

## Deploy to Render

The repository includes a [Render Blueprint](render.yaml) for the dashboard and API. Push the
repository to GitHub, create a Blueprint in Render, and select this repository. Render will create
two web services:

- **Dashboard:** Next.js, available at `/team/hackathon` on its Render URL.
- **API:** FastAPI, with `/health` and interactive docs at `/docs`.

Configure Nonilion to send webhook events to
`https://<agentsync-api-host>/webhook` (or `/webhook/nonilion`). In the Render `agentsync-api`
service, add `NONILION_SENDER_KEY` with the sender key as its value. The sender must send that key
as `Authorization: Bearer <sender-key>`. Save the environment variable and redeploy the API.

The API stores tasks, locks, events, and contracts in process memory. This is suitable for a demo;
state is lost on restart and is not shared between instances. Add persistent storage and webhook
authentication before using it with production data.

## Repository map

| Path | Purpose |
| --- | --- |
| `apps/agentsync-api` | FastAPI webhook and coordination MVP |
| `apps/web` | Next.js room and activity dashboard |
| `apps/daemon` | AgentSync CLI, agent hooks, coordination runtime, and local orchestration |
| `apps/coordinator` | Room coordination core and optional Cloudflare Durable Object host |
| `packages/protocol` | Event, message, and room-state schemas |
| `packages/reducer` | Deterministic room-state reducer |
| `packages/analysis`, `packages/contracts` | Symbol indexing and contract checks |
| `packages/simulator`, `demo-repo` | Local scenarios and sample project |

For the broader local runtime setup and commands, see [apps/daemon/README.md](apps/daemon/README.md).
