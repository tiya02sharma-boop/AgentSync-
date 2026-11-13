# AgentSync FastAPI backend

This standalone MVP service follows the AgentSync architecture brief. It receives Nonilion webhooks, keeps shared task and resource state, detects incompatible interface changes without relying on an LLM, and requires human approval before a proposed contract can be verified.

```bash
cd apps/agentsync-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The interactive API is available at `http://localhost:8000/docs`.

`nonilion-ready-main.py` is an alternate implementation copied in for review. Render continues to
run `main.py`; the alternate file is not active. Its Nonilion reply API assumptions need confirmation
before switching the service to it.

The webhook accepts JSON objects at both `/webhook` and `/webhook/nonilion`. To require sender
authentication, set `WEBHOOK_SECRET` (or the legacy `NONILION_SENDER_KEY`). Send the secret in
`Authorization: Bearer <secret>`, `X-Webhook-Secret: <secret>`, or `X-Sender-Key: <secret>`. If
neither environment variable is set, requests are accepted without sender-key validation. On
Render, set this secret in the `agentsync-api` service's Environment settings and redeploy. Do not
commit the secret to the repository.
