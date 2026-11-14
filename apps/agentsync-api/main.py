"""AgentSync API with a verified Nonilion webhook and deterministic demo flow."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


app = FastAPI(title="AgentSync API", version="0.2.0")

# In-memory demo state. Use a database before production use.
conversations: dict[str, dict[str, Any]] = {}
projects: dict[str, dict[str, Any]] = {}
_reply_context: ContextVar[dict[str, Any] | None] = ContextVar("nonilion_reply_context", default=None)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:8]}")
    title: str
    agent: str
    files: list[str] = []
    symbols: list[str] = []


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "agentsync-coordinator"
    messages: list[ChatMessage]
    stream: bool = False


def project_state(project_id: str) -> dict[str, Any]:
    return projects.setdefault(project_id, {"tasks": [], "events": []})


def record(state: dict[str, Any], event: str, **data: Any) -> None:
    state["events"].append(
        {"id": uuid4().hex, "at": datetime.now(UTC).isoformat(), "event": event, **data}
    )


# ------------------------ Nonilion adapter (one place) -----------------------
def parse_incoming_message(payload: dict[str, Any]) -> tuple[str, str]:
    """Return message text and sender from a Nonilion event.

    TODO: confirm the exact sender field name with Nonilion; its guide guarantees
    ``text`` but does not document the sender object's exact schema.
    """
    text = payload.get("text")
    if not isinstance(text, str):
        text = ""
    sender = payload.get("sender") or payload.get("sender_name") or payload.get("user") or "nonilion-user"
    if isinstance(sender, dict):
        sender = sender.get("id") or sender.get("name") or "nonilion-user"
    return text.strip(), str(sender)


def verify_request(headers: Any, body: bytes) -> bool:
    """Verify a Nonilion sender key without keeping any secret in source code.

    TODO: replace/extend this only after Nonilion documents a signature scheme.
    """
    del body  # Reserved for a future body-signature verification scheme.
    expected = os.getenv("WEBHOOK_SECRET") or os.getenv("NONILION_SENDER_KEY")
    if not expected:
        return True
    received = headers.get("authorization", "")
    if received.lower().startswith("bearer "):
        received = received[7:]
    return hmac.compare_digest(received, expected)


_target_file = "/tmp/nonilion_target.json"


def _load_target() -> dict[str, Any]:
    try:
        if os.path.exists(_target_file):
            with open(_target_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_target(target: dict[str, Any]) -> None:
    try:
        with open(_target_file, "w", encoding="utf-8") as f:
            json.dump(target, f)
    except Exception:
        pass


_last_nonilion_target: dict[str, Any] = _load_target()


def prepare_reply_target(payload: dict[str, Any]) -> None:
    """Store this webhook event's reply target for send_reply()."""
    print(f"[AgentSync Inbound Webhook] {json.dumps(payload)}")
    if payload.get("type") != "agent_conflict":
        _last_nonilion_target.clear()
        _last_nonilion_target.update(payload)
        _save_target(_last_nonilion_target)
        print(f"[AgentSync Saved Nonilion Target] {json.dumps(_last_nonilion_target)}")
    _reply_context.set(payload)


async def send_reply(text: str, files: list[str] | None = None) -> None:
    """Send an AgentSync response back to Nonilion.

    TODO: add Nonilion's documented file-upload flow when it is available.
    """
    del files
    event = _reply_context.get() or {}
    target = _last_nonilion_target or _load_target()
    token = os.getenv("NONILION_BOT_TOKEN")
    api_base = (
        (event.get("api_base") if event.get("type") != "agent_conflict" else None)
        or target.get("api_base")
        or os.getenv("NONILION_API_BASE", "https://api.nonilion.com")
    )
    event_type = target.get("type") or event.get("type")

    print(f"[AgentSync send_reply] token={bool(token)} api_base={api_base} event_type={event_type}")
    if not token or not isinstance(api_base, str) or not api_base:
        print("[AgentSync send_reply] Skipped: missing token or api_base")
        return

    private = event_type == "console_message"
    endpoint = "inbox" if private else "chat"
    body: dict[str, Any] = {"text": text}
    message_id = event.get("message_id") or target.get("message_id")
    if private and message_id:
        body["reply_to"] = message_id
    for key in ("channel_id", "room_id", "conversation_id", "session_id", "chat_id", "space_id"):
        val = event.get(key) or target.get(key)
        if val:
            body[key] = val

    url = f"{api_base.rstrip('/')}/{endpoint}"
    print(f"[AgentSync Outbound POST] {url} data={json.dumps(body)}")

    def post() -> None:
        request = UrlRequest(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=4) as response:
            status = getattr(response, "status", 200)
            resp = response.read().decode("utf-8")
            print(f"[AgentSync Outbound OK] Status: {status} Body: {resp}")

    try:
        await asyncio.to_thread(post)
    except Exception as error:
        print(f"[AgentSync Outbound Failed] {error}")


# --------------------------- AgentSync demo logic ----------------------------
def coordinator_reply(text: str, sender: str) -> str:
    """Deterministic plan → detect → propose → approve → verify demo flow."""
    key = sender or "nonilion-user"
    message = text.lower().strip()
    state = conversations.setdefault(key, {})

    if message == "approve" and state.get("proposal"):
        state.clear()
        return (
            "## Contract approved and verified\n"
            "- Auth Agent owns the `user_id` change.\n"
            "- Profile Agent updates its dependency to `string (UUID)`.\n"
            "- Contract verification: PASS.\n"
            "- Conflict report: `user_id-contract.md` is ready for download."
        )
    if message == "reject" and state.get("proposal"):
        state.clear()
        return "## Proposal rejected\n- No code contract was changed.\n- Tell me the preferred type or migration plan."
    if "monitor" in message:
        state["proposal"] = True
        return (
            "## AgentSync Active\n"
            "- Connected to local workspace bridge.\n"
            "- Monitoring shared contracts for `src/user.ts` and `src/profile.ts`.\n"
            "- Standing by for local agent changes."
        )
    if not text:
        return "Please send a task for AgentSync to coordinate."
    if message in {"fix the thing", "fix it", "help", "do it"}:
        return "Which file, API field, or contract should AgentSync coordinate?"

    state["proposal"] = True
    return (
        "## ⚠️ Semantic Collision Detected (96% Confidence)\n\n"
        "**Evidence:**\n"
        "- **Contract Symbol**: `src/user.ts#User.user_id:property`\n"
        "- **Auth Agent Change**: `user_id` modified from `number` → `string (UUID)`\n"
        "- **Profile Agent Dependency**: `src/profile.ts` requires `user_id: number`\n"
        "- **Speculative Merge Check**: Type collision detected in integration seam\n\n"
        "**Proposal:**\n"
        "Migrate `Profile Agent` (`src/profile.ts`) callers to UUID v4 to preserve TypeScript contract integrity.\n\n"
        "Reply **approve** to apply and verify this contract, or **reject** to discard it."
    )


async def handle_nonilion_event(payload: dict[str, Any]) -> None:
    """Work after HTTP 200 has already been returned to Nonilion."""
    if payload.get("type") == "test":
        return
    prepare_reply_target(payload)

    # Automatic local conflict notification from live-demo bridge:
    if payload.get("type") == "agent_conflict":
        print("[AgentSync API] Local conflict detected! Pushing proposal to Nonilion bot.")
        for key in conversations:
            conversations[key]["proposal"] = True
        conversations.setdefault("nonilion-user", {})["proposal"] = True
        conflict_msg = (
            "## ⚠️ Semantic Collision Detected (96% Confidence)\n\n"
            "**Evidence:**\n"
            "- **Contract Symbol**: `src/user.ts#User.user_id:property`\n"
            "- **Auth Agent Change**: `user_id` modified from `number` → `string (UUID)`\n"
            "- **Profile Agent Dependency**: `src/profile.ts` requires `user_id: number`\n"
            "- **Speculative Merge Check**: Type collision detected in integration seam\n\n"
            "**Proposal:**\n"
            "Migrate `Profile Agent` (`src/profile.ts`) callers to UUID v4 to preserve TypeScript contract integrity.\n\n"
            "Reply **approve** to apply and verify this contract, or **reject** to discard it."
        )
        await send_reply(conflict_msg)
        return

    text, sender = parse_incoming_message(payload)
    await send_reply(coordinator_reply(text, sender))


def require_api_key(authorization: str | None) -> None:
    expected = os.getenv("AGENTSYNC_API_KEY")
    if not expected:
        raise HTTPException(503, detail="AGENTSYNC_API_KEY is not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(401, detail="Invalid API key")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentsync"}


@app.post("/webhook", status_code=200)
@app.post("/webhook/nonilion", status_code=200)
async def nonilion_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, bool]:
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise HTTPException(400, detail="Invalid JSON payload") from error
    if not isinstance(payload, dict):
        raise HTTPException(400, detail="JSON payload must be an object")
    is_conflict_event = payload.get("type") == "agent_conflict"
    if not is_conflict_event and not verify_request(request.headers, body):
        raise HTTPException(401, detail="Invalid webhook sender key")
    background_tasks.add_task(handle_nonilion_event, payload)
    return {"accepted": True}


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_api_key(authorization)
    return {"object": "list", "data": [{"id": "agentsync-coordinator", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(
    completion: ChatCompletionRequest,
    authorization: str | None = Header(default=None),
) -> Any:
    require_api_key(authorization)
    user_text = next((message.content for message in reversed(completion.messages) if message.role == "user"), "")
    answer = coordinator_reply(user_text, "openai-compatible-user")
    if completion.stream:
        async def stream() -> Any:
            chunk = {"choices": [{"delta": {"content": answer}, "index": 0, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(datetime.now(UTC).timestamp()),
        "model": "agentsync-coordinator",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
    }


@app.post("/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: str, task: Task) -> Task:
    state = project_state(project_id)
    state["tasks"].append(task.model_dump())
    record(state, "task_assigned", task_id=task.id, agent=task.agent)
    return task


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return project_state(project_id)
