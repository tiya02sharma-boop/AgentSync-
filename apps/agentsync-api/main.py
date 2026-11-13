"""AgentSync's small FastAPI webhook and deterministic coordination MVP.

Run locally with:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


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


@app.post("/webhook/nonilion", status_code=202)
def nonilion_webhook(event: WebhookEvent) -> dict[str, Any]:
    """Accept a Nonilion Bot API event and deterministically detect API conflicts.

    LLMs can later explain or propose a resolution, but conflict detection here depends
    only on declared symbols and incompatible before/after interface values.
    """
    state = project_state(event.project_id)
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
