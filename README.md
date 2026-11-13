# AgentSync

AgentSync is a coordination layer for teams using multiple coding agents. It makes task ownership
and shared code resources visible, flags incompatible interface changes, and gives people a chance
to approve a proposed contract before it is marked verified.

This repository contains a FastAPI webhook/task API, a Next.js activity dashboard, and the
Agentigram WebSocket coordinator and agent runtime. The dashboard connects to the WebSocket
coordinator; the FastAPI API is a separate MVP used for webhooks and task/contract endpoints.

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

The repository includes a [Render Blueprint](render.yaml) for the dashboard and FastAPI API. The
dashboard's live room stream also requires the WebSocket coordinator in `apps/coordinator`, which
uses Cloudflare Durable Objects and must be deployed separately:

```bash
corepack enable
pnpm install
pnpm --filter @agentigram/coordinator deploy
```

After deployment, copy the Cloudflare Worker URL. In the Render `agentigram-dashboard` service, set
`NEXT_PUBLIC_COORDINATOR_URL` to its secure WebSocket URL (change `https://` to `wss://`), such as
`wss://agentigram-coordinator.<your-subdomain>.workers.dev`, and set `NEXT_PUBLIC_ROOM_TOKEN` to the
same value configured as the coordinator's `ROOM_SECRET`. These `NEXT_PUBLIC_*` values are embedded
at build time, so save them and trigger a new deploy. The room token is visible to dashboard users;
the coordinator limits dashboard submissions to human actions, but the coordinator's M1 auth is a
demo-level shared-token scheme, not production user authentication.

To show events from the local AgentSync daemon in that hosted dashboard, deploy the coordinator
with a separate `BRIDGE_SECRET`:

```bash
pnpm --filter @agentigram/coordinator exec wrangler secret put BRIDGE_SECRET
```

Set `AGENTSYNC_BRIDGE_URL` to the Worker HTTPS URL and
`AGENTSYNC_BRIDGE_SECRET` to the same secret in the authority daemon's environment. Restart that
daemon after setting them. It will replay unsent room events and forward new events to the hosted
room. Open `/team/<room-id>` on the dashboard; for the default local `agentsync-live` room, use
`/team/agentsync-live`. Never use `ROOM_SECRET`, `WEBHOOK_SECRET`, or a Nonilion token as the bridge
secret.

The Render Blueprint creates two web services:

- **Dashboard:** Next.js, available at `/team/hackathon` on its Render URL.
- **API:** FastAPI, with `/health` and interactive docs at `/docs`.

Without the separately deployed coordinator and these two Render variables, the dashboard falls
back to its labeled rehearsal data; deploying the FastAPI API alone does not provide the live room
WebSocket.

Configure Nonilion to send webhook events to
`https://<agentsync-api-host>/webhook` (or `/webhook/nonilion`). In the Render `agentsync-api`
service, set `WEBHOOK_SECRET` to the webhook secret. The receiver accepts it in the `Authorization:
Bearer ...`, `X-Webhook-Secret`, or `X-Sender-Key` header. `NONILION_SENDER_KEY` remains supported as
a legacy environment-variable name. Save the environment variable and redeploy the API.

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
