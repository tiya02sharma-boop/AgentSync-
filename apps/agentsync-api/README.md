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
