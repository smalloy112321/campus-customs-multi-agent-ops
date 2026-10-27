"""The Campus Customs team: one MCP connection, five agents, and the agent loop.

Every agent reaches shop data only through the campus-customs MCP server
(configured in .mcp.json), each through its own filtered slice of tools. Each
step of each agent loop is appended to output/audit_trail.json as it happens.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastmcp import Client
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_core import to_jsonable_python

from backend import audit
from backend.agents import SPECS
from backend.agents.base import MODEL_FAILURES, build_agent
from backend.config import (
    INPUT_TOKENS_PER_REQUEST,
    MODEL_NAME,
    REQUEST_LIMIT_PER_TICKET,
    TOTAL_TOKENS_PER_TICKET,
    is_allowed_model,
    load_mcp_config,
    make_model,
)
from backend.models import AgentName, BossCall, BossDecision, DelegationBudget, TeamDeps

# One budget per ticket: usage is shared across the whole delegation tree, so these caps
# apply to the ticket, not to each agent.
TICKET_LIMITS = UsageLimits(
    request_limit=REQUEST_LIMIT_PER_TICKET,
    total_tokens_limit=TOTAL_TOKENS_PER_TICKET,
    per_request_input_tokens_limit=INPUT_TOKENS_PER_REQUEST,
)


def _mcp_client() -> Client:
    """The same campus-customs server entry the vibe coder uses, read from .mcp.json."""
    return Client(load_mcp_config())


def _json(value: Any) -> Any:
    return to_jsonable_python(value, fallback=str)


def _parts(parts: Any) -> list[dict]:
    out = []
    for p in parts:
        kind = p.part_kind
        if kind == "system-prompt":
            out.append({"kind": kind, "note": "agent prompt from backend/prompts/"})
            continue
        item: dict[str, Any] = {"kind": kind}
        for attr in ("tool_name", "tool_call_id"):
            if getattr(p, attr, None):
                item[attr] = getattr(p, attr)
        if kind == "tool-call":
            item["args"] = p.args_as_dict()
        elif hasattr(p, "content"):
            item["content"] = _json(p.content)
        out.append(item)
    return out


class ModelNotAllowed(RuntimeError):
    pass


class Team:
    """Use as `async with Team() as team:` so the MCP connection is open for the run."""

    def __init__(self) -> None:
        self.model = make_model()
        self.client = _mcp_client()
        self.mcp = MCPToolset(self.client, max_retries=2)
        self.agents: dict[str, Agent] = {
            name: build_agent(spec, self.model, self.mcp) for name, spec in SPECS.items()
        }

    async def __aenter__(self) -> Team:
        await self.mcp.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        try:
            await self.mcp.__aexit__(*exc)
        finally:
            await self.client.close()  # stdio servers are kept alive by default; stop ours

    # -- MCP calls the runner makes itself (not on behalf of an agent) --------

    async def call_tool(self, name: str, args: dict | None = None) -> dict:
        async with self.client:
            result = await self.client.call_tool(name, args or {})
        return result.structured_content

    # -- The agent loop ---------------------------------------------------------

    async def run_agent(
        self,
        name: AgentName,
        task: str,
        *,
        run_id: str,
        ticket_id: int | None,
        parent: AgentName | None = None,
        depth: int = 0,
        chain: list[AgentName] | None = None,
        budget: DelegationBudget | None = None,
        usage: RunUsage | None = None,
    ) -> Any:
        agent = self.agents[name]
        deps = TeamDeps(team=self, run_id=run_id, agent=name, ticket_id=ticket_id, depth=depth,
                        chain=chain or [], budget=budget or DelegationBudget())
        where = dict(run_id=run_id, ticket_id=ticket_id, agent=name, parent_agent=parent, depth=depth)
        audit.log(**where, step=0, event="run_start", model=MODEL_NAME, task=task,
                  prompt_file=SPECS[name].prompt_file, chain=deps.chain)

        step = 0
        try:
            async with agent.iter(
                task,
                deps=deps,
                usage=usage,
                usage_limits=TICKET_LIMITS,
            ) as run:
                async for node in run:
                    step += 1
                    if Agent.is_user_prompt_node(node):
                        audit.log(**where, step=step, event="user_prompt", prompt=_json(node.user_prompt))
                    elif Agent.is_model_request_node(node):
                        audit.log(**where, step=step, event="model_request", model=MODEL_NAME,
                                  parts=_parts(node.request.parts))
                    elif Agent.is_call_tools_node(node):
                        response = node.model_response
                        allowed = is_allowed_model(response.model_name)
                        audit.log(**where, step=step, event="model_response", model=response.model_name,
                                  model_allowed=allowed, parts=_parts(response.parts),
                                  usage=_json(response.usage), finish_reason=response.finish_reason)
                        if not allowed:
                            raise ModelNotAllowed(
                                f"Response came from '{response.model_name}', not {MODEL_NAME}. Stopping."
                            )
                output = run.result.output
        except Exception as exc:
            audit.log(**where, step=step + 1, event="error", error_type=type(exc).__name__, error=str(exc))
            raise

        audit.log(**where, step=step + 1, event="run_end", model=MODEL_NAME, output=_json(output),
                  usage=_json(run.usage))
        return output

    async def run_ticket(self, ticket_id: int) -> BossDecision:
        """The Boss works one ticket end to end, delegating as needed."""
        task = (
            f"Work ticket {ticket_id}. Read it with get_ticket, delegate to the specialists it "
            "needs, verify their facts, record your decision with update_ticket, and return "
            "your final call (ticket_id, final_status, decision)."
        )
        run_id = f"ticket-{ticket_id}-{uuid.uuid4().hex[:8]}"
        started = datetime.now().astimezone()
        try:
            call: BossCall = await self.run_agent("boss", task, run_id=run_id, ticket_id=ticket_id)
            recovered = False
        except MODEL_FAILURES as exc:
            call = await self._recover_from_board(ticket_id, run_id, started, exc)
            recovered = True

        decision = await self._full_decision(call, run_id, recovered)
        audit.log(run_id=run_id, ticket_id=ticket_id, agent="system", step=0, event="boss_decision",
                  decision=_json(decision))
        # The run is over: resolve the ticket unless a payment is still waiting on a human.
        closed = await self.call_tool("resolve_ticket_after_run", {"ticket_id": ticket_id,
                                                                  "note": f"Boss: {decision.decision}"})
        audit.log(run_id=run_id, ticket_id=ticket_id, agent="system", step=0, event="ticket_closed"
                  if closed.get("resolved") else "awaiting_human", result=closed)
        return decision

    # -- Reliability: finish the ticket from the board if the Boss's last answer never comes ------

    async def _boss_updates_since(self, ticket_id: int, started: datetime) -> tuple[dict, list[dict]]:
        board = await self.call_tool("get_ticket", {"ticket_id": ticket_id})
        mine = [u for u in board.get("ticket_updates", [])
                if u["agent"] == "boss" and datetime.fromisoformat(u["created_at"]) >= started.replace(microsecond=0)]
        return board, mine

    async def _recover_from_board(self, ticket_id: int, run_id: str, started: datetime, exc: Exception) -> BossCall:
        """The Boss failed after every retry. If it had already recorded its decision with
        update_ticket in this run, take the call from there; otherwise the run really failed."""
        board, updates = await self._boss_updates_since(ticket_id, started)
        if not updates:
            raise exc
        last = updates[-1]
        call = BossCall(ticket_id=ticket_id, final_status=last["status"] or board["ticket"]["status"],
                        decision=last["note"])
        audit.log(run_id=run_id, ticket_id=ticket_id, agent="system", step=0, event="boss_output_recovered",
                  error=f"{type(exc).__name__}: {exc}", from_update=last)
        # Close the Boss's loop in the trail so every reader sees its call, marked as recovered.
        audit.log(run_id=run_id, ticket_id=ticket_id, agent="boss", step=0, event="run_end", model=MODEL_NAME,
                  output={**call.model_dump(), "recovered_from_board": True})
        return call

    async def _full_decision(self, call: BossCall, run_id: str, recovered: bool) -> BossDecision:
        """The Boss's own call plus what the board and the audit trail show for this run."""
        board = await self.call_tool("get_ticket", {"ticket_id": call.ticket_id})
        run = audit.read_run(run_id)
        consulted: list[AgentName] = []
        for e in run:
            if e["event"] == "run_start" and e["agent"] != "boss" and e["agent"] not in consulted:
                consulted.append(e["agent"])
        delegations = [
            f"{e['agent']} -> {(p.get('args') or {}).get('to')}"
            for e in run if e["event"] == "model_response"
            for p in e["detail"].get("parts", []) if p.get("kind") == "tool-call" and p.get("tool_name") == "delegate"
        ]
        boss_notes = [u["note"] for u in board.get("ticket_updates", []) if u["agent"] == "boss"]
        pending = [r for r in board.get("payment_requests", []) if r["status"] == "pending"]
        steps = [f"Approve or reject payment request #{r['id']}: ${r['amount']:,.2f} {r['kind'].replace('_', ' ')} "
                 f"to {r['payee']}" for r in pending]
        steps += [f"Review draft #{d['id']} to {d['recipient']} (not sent)" for d in board.get("drafts", [])]
        return BossDecision(
            ticket_id=call.ticket_id,
            decision=call.decision,
            final_status=call.final_status,
            rationale=boss_notes[-1] if boss_notes else call.decision,
            agents_consulted=consulted,
            delegations=delegations,
            payment_request_ids=[r["id"] for r in board.get("payment_requests", [])],
            purchase_order_ids=[po["id"] for po in board.get("purchase_orders", [])],
            draft_ids=[d["id"] for d in board.get("drafts", [])],
            next_steps_for_human=steps,
            recovered_from_board=recovered,
        )
