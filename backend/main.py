"""Campus Customs backend: the routes the React dashboard calls.

Start from the backend/ folder:

    uvicorn main:app --reload --port 8000

Every shop fact goes through the campus-customs MCP server (.mcp.json), the same
one the agents use. Agents only *prepare* payments; the approve route below is
the only path that moves cash, and it records the human who clicked approve.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

# Running from backend/ (uvicorn main:app): make the project root importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import audit  # noqa: E402
from backend.config import AUDIT_PATH, MODEL_NAME  # noqa: E402
from backend.efficiency import measure  # noqa: E402
from backend.team import Team, _mcp_client  # noqa: E402
from mcp_server.reset_db import reset_database  # noqa: E402

EVENT_TEXT_LIMIT = 400  # characters of tool results / outputs shown per event

mcp = _mcp_client()

# One run at a time: tickets share one checking account, so runs must not overlap.
RUNS: dict[int, dict[str, Any]] = {}
_run_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp:  # keep one MCP connection open for the routes
        yield


app = FastAPI(title="Campus Customs Multi-Agent Operations", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


async def call_mcp(tool: str, args: dict | None = None) -> dict:
    result = await mcp.call_tool(tool, args or {})
    return result.structured_content


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _active_run() -> int | None:
    return next((tid for tid, r in RUNS.items() if r["state"] == "running"), None)


# ---------------------------------------------------------------------------
# 1. Tickets
# ---------------------------------------------------------------------------


@app.get("/api/tickets")
async def list_tickets() -> dict:
    """Every ticket with its board status and open/resolved. A resolved ticket also carries
    the efficiency score of its latest run (the Problem 6 meter)."""
    board = await call_mcp("list_tickets")
    entries = _current_entries()
    tickets = []
    for t in board["tickets"]:
        state = "resolved" if t["is_resolved"] else "open"
        tickets.append({
            **t,
            "state": state,
            "efficiency": measure(t["id"], entries) if state == "resolved" else None,
            "run": RUNS.get(t["id"]),
        })
    return {"count": len(tickets), "tickets": tickets, "active_run": _active_run()}


@app.get("/api/tickets/{ticket_id}/summary")
async def ticket_summary(ticket_id: int) -> dict:
    """Short summary of the latest run: the Boss's call, each specialist's report, and what
    is on the board for the ticket (drafts, payment requests, purchase orders)."""
    board = await call_mcp("get_ticket", {"ticket_id": ticket_id})
    if not board.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}.")
    entries = [e for e in _current_entries()
               if e.get("ticket_id") == ticket_id and str(e.get("run_id", "")).startswith(f"ticket-{ticket_id}-")]
    if not entries:
        return {"ticket_id": ticket_id, "ran": False, "board": board}
    run_id = entries[-1]["run_id"]
    run = [e for e in entries if e["run_id"] == run_id]
    reports = []
    for e in run:
        if e["event"] != "run_end":
            continue
        out = e["detail"].get("output") or {}
        reports.append({
            "agent": e["agent"],
            "parent_agent": e.get("parent_agent"),
            "summary": out.get("decision") or out.get("summary"),
            "recommendation": out.get("recommendation"),
            "blockers": out.get("blockers", []),
            "actions_taken": out.get("actions_taken", []),
        })
    boss = next((e["detail"]["output"] for e in reversed(run) if e["event"] == "run_end" and e["agent"] == "boss"), None)
    return {
        "ticket_id": ticket_id,
        "ran": True,
        "run_id": run_id,
        "started_at": run[0]["timestamp"],
        "finished_at": run[-1]["timestamp"],
        "boss": boss,
        "reports": [r for r in reports if r["agent"] != "boss"],
        "board": board,
    }


@app.get("/api/tickets/{ticket_id}/efficiency")
async def ticket_efficiency(ticket_id: int) -> dict:
    """Efficiency score of a ticket's latest run against its plan, open or resolved."""
    result = measure(ticket_id, _current_entries())
    if result is None:
        raise HTTPException(404, f"No agent run for ticket {ticket_id} since the last reset.")
    return result


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int) -> dict:
    """One ticket with its board history: updates, drafts, purchase orders, payment requests."""
    result = await call_mcp("get_ticket", {"ticket_id": ticket_id})
    if not result.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}.")
    return {**result, "run": RUNS.get(ticket_id)}


# ---------------------------------------------------------------------------
# 2. Run the agent team on a ticket
# ---------------------------------------------------------------------------


async def _run_ticket(ticket_id: int) -> None:
    run = RUNS[ticket_id]
    try:
        async with Team() as team:
            decision = await team.run_ticket(ticket_id)
        run.update(state="done", decision=decision.model_dump())
    except Exception as exc:  # recorded for the dashboard; details are in the audit trail
        run.update(state="error", error=f"{type(exc).__name__}: {exc}")
    finally:
        run["finished_at"] = _now()


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    """Start the agent team on one ticket. Returns at once; poll /api/events or /api/tickets."""
    found = await call_mcp("get_ticket", {"ticket_id": ticket_id})
    if not found.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}.")
    if found["ticket"]["status"] in ("resolved", "declined"):
        raise HTTPException(409, f"Ticket {ticket_id} is already {found['ticket']['status']}. Reset to run it again.")
    async with _run_lock:
        if (active := _active_run()) is not None:
            raise HTTPException(409, f"Ticket {active} is still running. Runs go one at a time.")
        RUNS[ticket_id] = {"ticket_id": ticket_id, "state": "running", "started_at": _now(),
                           "finished_at": None, "model": MODEL_NAME, "decision": None, "error": None}
        asyncio.create_task(_run_ticket(ticket_id))
    return RUNS[ticket_id]


@app.get("/api/runs")
async def list_runs() -> dict:
    """State of each ticket's latest run since the server started."""
    return {"active_run": _active_run(), "runs": list(RUNS.values())}


# ---------------------------------------------------------------------------
# 3. Recent agent events (from output/audit_trail.json)
# ---------------------------------------------------------------------------


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= EVENT_TEXT_LIMIT else text[:EVENT_TEXT_LIMIT] + "…"


def _event_view(index: int, e: dict) -> dict:
    """Flatten one audit entry into what the board shows: who, what they said, which tools."""
    d = e.get("detail", {})
    parts = d.get("parts", [])
    said = [p["content"] for p in parts if p.get("kind") == "text" and p.get("content")]
    tool_calls = [
        {"tool": p["tool_name"], "args": p.get("args", {})}
        for p in parts
        if p.get("kind") == "tool-call" and p.get("tool_name") != "final_result"
    ]
    tool_results = [
        {"tool": p["tool_name"], "result": _short(p.get("content"))}
        for p in parts
        if p.get("kind") == "tool-return" and p.get("tool_name") != "final_result"
    ]
    view = {
        "index": index,
        "timestamp": e.get("timestamp"),
        "run_id": e.get("run_id"),
        "ticket_id": e.get("ticket_id"),
        "agent": e.get("agent"),
        "parent_agent": e.get("parent_agent"),
        "depth": e.get("depth", 0),
        "step": e.get("step"),
        "event": e.get("event"),
        "model": e.get("model"),
        "said": said,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    }
    if e.get("event") == "run_start":
        view["task"] = d.get("task")
    elif e.get("event") == "run_end":
        output = d.get("output") or {}
        view["output"] = output
        view["said"] = said or [output.get("decision") or output.get("summary") or ""]
    elif e.get("event") in ("error", "delegation_refused", "db_reset", "human_decision"):
        view["detail"] = d
    return view


def _read_audit() -> list[dict]:
    if not AUDIT_PATH.exists() or not AUDIT_PATH.stat().st_size:
        return []
    return json.loads(AUDIT_PATH.read_text())  # atomically replaced on write, so always whole


def _last_reset_index(entries: list[dict]) -> int:
    """Index of the most recent db_reset event (-1 if none). Runs before it describe a shop
    state that no longer exists, so the board only shows what came after."""
    return next((i for i in range(len(entries) - 1, -1, -1) if entries[i].get("event") == "db_reset"), -1)


def _current_entries() -> list[dict]:
    entries = _read_audit()
    return entries[_last_reset_index(entries) + 1:]


@app.get("/api/events")
async def recent_events(
    limit: int = Query(50, ge=1, le=500),
    since: int | None = Query(None, ge=0, description="Only events after this index (for polling)"),
    ticket_id: int | None = None,
    run_id: str | None = None,
    include_history: bool = Query(False, description="Also return events from before the last reset"),
) -> dict:
    """Recent agent events, newest last. Pass the returned `next_since` back as `since` to poll.
    By default only events since the last database reset are returned."""
    entries = _read_audit()
    views = [_event_view(i, e) for i, e in enumerate(entries)]
    if not include_history:
        views = views[_last_reset_index(entries) + 1:]
    if since is not None:
        views = [v for v in views if v["index"] > since]
    if ticket_id is not None:
        views = [v for v in views if v["ticket_id"] == ticket_id]
    if run_id is not None:
        views = [v for v in views if v["run_id"] == run_id]
    return {"total": len(entries), "next_since": len(entries) - 1, "events": views[-limit:]}


# ---------------------------------------------------------------------------
# 4. Human approval (the only route that moves cash)
# ---------------------------------------------------------------------------


class Decision(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human who clicked")
    note: str = ""


@app.get("/api/approvals")
async def pending_approvals() -> dict:
    """Payment and purchase-order requests the agents prepared, waiting for a human."""
    return await call_mcp("list_pending_approvals")


def _log_human(request_id: int, action: str, who: str, result: dict) -> None:
    audit.log(run_id=f"human-{uuid.uuid4().hex[:8]}", ticket_id=None, agent="human", step=0,
              event="human_decision", request_id=request_id, action=action, by=who, result=result)


@app.post("/api/approvals/{request_id}/approve")
async def approve(request_id: int, body: Decision) -> dict:
    """Human clicked approve: pay the request. Refused if cash would go negative."""
    result = await call_mcp("approve_payment", {"request_id": request_id, "approved_by": body.approved_by,
                                                "note": body.note})
    _log_human(request_id, "approve", body.approved_by, result)
    if not result.get("ok"):
        raise HTTPException(409 if result.get("refused") else 400, result.get("message"))
    return result


@app.post("/api/approvals/{request_id}/reject")
async def reject(request_id: int, body: Decision) -> dict:
    """Human clicked reject: no money moves."""
    result = await call_mcp("reject_payment", {"request_id": request_id, "rejected_by": body.approved_by,
                                               "note": body.note})
    _log_human(request_id, "reject", body.approved_by, result)
    if not result.get("ok"):
        raise HTTPException(400, result.get("message"))
    return result


# ---------------------------------------------------------------------------
# 5. Cash
# ---------------------------------------------------------------------------


@app.get("/api/cash")
async def cash() -> dict:
    """Current checking balance from cash_accounts, plus what is waiting for approval."""
    result = await call_mcp("check_cash")
    checking = next((a for a in result["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(500, "No checking account in cash_accounts.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["as_of"],
        "pending_requests_total": checking["pending_requests_total"],
        "balance_if_all_pending_approved": checking["balance_if_all_pending_approved"],
        "payments_made": result["payments_made"],
    }


# ---------------------------------------------------------------------------
# 6. Reset
# ---------------------------------------------------------------------------


@app.post("/api/reset")
async def reset() -> dict:
    """Copy the original database over the working copy. The audit trail is kept."""
    async with _run_lock:
        if (active := _active_run()) is not None:
            raise HTTPException(409, f"Ticket {active} is still running; reset after it finishes.")
        result = reset_database()
        RUNS.clear()
    audit.log(run_id=f"reset-{uuid.uuid4().hex[:8]}", ticket_id=None, agent="system", step=0,
              event="db_reset", source="api", **result)
    return result


@app.get("/api/health")
async def health() -> dict:
    """Liveness, the model, the active run, and the shop's 'today' (desk.date_today)."""
    desk = await call_mcp("get_shop_today")
    return {"ok": True, "model": MODEL_NAME, "active_run": _active_run(), "shop_today": desk["date_today"]}
