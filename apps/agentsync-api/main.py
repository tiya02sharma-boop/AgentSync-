"""AgentSync's small FastAPI webhook and deterministic coordination MVP.

Run locally with:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError


app = FastAPI(title="AgentSync API", version="0.1.0")


class AgentStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting_for_dependency"
    CONFLICTED = "conflict_detected"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:8]}")
    title: str
    agent: str
    files: list[str] = []
    symbols: list[str] = []
    depends_on: list[str] = []
    status: AgentStatus = AgentStatus.WORKING


class Contract(BaseModel):
    id: str = Field(default_factory=lambda: f"contract-{uuid4().hex[:8]}")
    symbol: str
    before: str
    after: str
    proposal: str
    approved: bool = False
    verified: bool = False


class WebhookEvent(BaseModel):
    project_id: str = "hackathon"
    kind: str
    agent: str
    file: str | None = None
    symbol: str | None = None
    before: str | None = None
    after: str | None = None
    message: str | None = None


projects: dict[str, dict[str, Any]] = {}


def project_state(project_id: str) -> dict[str, Any]:
    return projects.setdefault(
        project_id,
        {"tasks": [], "contracts": [], "events": [], "locks": {}},
    )


def record(state: dict[str, Any], event: str, **data: Any) -> dict[str, Any]:
    item = {"id": uuid4().hex, "at": datetime.now(UTC).isoformat(), "event": event, **data}
    state["events"].append(item)
    return item


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentsync"}


@app.post("/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: str, task: Task) -> Task:
    """Register planner output and reserve declared resources for its worker."""
    state = project_state(project_id)
    for resource in [*task.files, *task.symbols]:
        holder = state["locks"].get(resource)
        if holder and holder != task.agent:
            raise HTTPException(409, detail=f"{resource} is reserved by {holder}")
        state["locks"][resource] = task.agent
    state["tasks"].append(task)
    record(state, "task_assigned", task_id=task.id, agent=task.agent, resources=[*task.files, *task.symbols])
    return task


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    """Shared state for the Nonilion activity room or web dashboard."""
    return project_state(project_id)


@app.post("/webhook", status_code=200)
@app.post("/webhook/nonilion", status_code=200)
async def nonilion_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    sender_key: str | None = Header(default=None, alias="X-Sender-Key"),
) -> dict[str, Any]:
    """Accept Nonilion JSON events, optionally authenticating its sender key.

    Recognized AgentSync event fields retain deterministic conflict detection. Other JSON
    objects are accepted and recorded by their field names for webhook compatibility.
    """
    expected_secret = os.getenv("WEBHOOK_SECRET") or os.getenv("NONILION_SENDER_KEY")
    if expected_secret:
        received_values = [webhook_secret or "", sender_key or ""]
        auth_value = authorization or ""
        if auth_value[:7].lower() == "bearer ":
            auth_value = auth_value[7:]
        received_values.append(auth_value)
        if not any(hmac.compare_digest(value, expected_secret) for value in received_values):
            raise HTTPException(status_code=401, detail="Invalid sender key")

    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON payload must be an object")

    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        project_id = "hackathon"
    state = project_state(project_id)
    try:
        event = WebhookEvent.model_validate(payload)
    except ValidationError:
        record(state, "nonilion_event", payload_keys=sorted(payload.keys()))
        return {"accepted": True, "conflict": None}

    record(state, "nonilion_event", **event.model_dump(exclude_none=True))
    if event.kind != "api_change" or not all([event.symbol, event.before, event.after]):
        return {"accepted": True, "conflict": None}

    consumers = [task for task in state["tasks"] if event.symbol in task.symbols and task.agent != event.agent]
    if not consumers:
        return {"accepted": True, "conflict": None}

    contract = Contract(
        symbol=event.symbol,
        before=event.before,
        after=event.after,
        proposal=(
            f"Update every consumer of {event.symbol} from {event.before} to {event.after} "
            "before releasing the owner lock."
        ),
    )
    state["contracts"].append(contract)
    record(state, "conflict_detected", contract_id=contract.id, affected=[task.agent for task in consumers])
    return {"accepted": True, "conflict": contract}


@app.post("/projects/{project_id}/contracts/{contract_id}/approve")
def approve_contract(project_id: str, contract_id: str) -> Contract:
    state = project_state(project_id)
    contract = next((item for item in state["contracts"] if item.id == contract_id), None)
    if not contract:
        raise HTTPException(404, detail="contract not found")
    contract.approved = True
    record(state, "contract_approved", contract_id=contract.id)
    return contract


@app.post("/projects/{project_id}/contracts/{contract_id}/verify")
def verify_contract(project_id: str, contract_id: str) -> Contract:
    state = project_state(project_id)
    contract = next((item for item in state["contracts"] if item.id == contract_id), None)
    if not contract:
        raise HTTPException(404, detail="contract not found")
    if not contract.approved:
        raise HTTPException(409, detail="human approval is required before verification")
    contract.verified = True
    record(state, "contract_verified", contract_id=contract.id)
    return contract
