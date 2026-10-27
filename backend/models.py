"""Data types for the Campus Customs agent team: agent outputs, run dependencies,
and the audit trail entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from backend.team import Team

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "waiting_approval", "waiting_vendor", "resolved", "declined"]


# ---------------------------------------------------------------------------
# Agent outputs
# ---------------------------------------------------------------------------


class Fact(BaseModel):
    """One value read from an MCP tool. Every claim an agent makes must trace to one."""

    tool: str = Field(description="MCP tool that returned the value, e.g. check_stock")
    field: str = Field(description="Field name in the tool output, e.g. on_hand")
    value: str = Field(description="The value exactly as the tool returned it")


class SpecialistReport(BaseModel):
    """What a specialist (inventory, accounting, facilities, customer_service) hands back."""

    agent: AgentName
    ticket_id: int | None = None
    summary: str = Field(description="Two to four sentences on what you found and did")
    facts: list[Fact] = Field(default_factory=list, description="Tool-sourced values backing the summary")
    actions_taken: list[str] = Field(default_factory=list, description="Writes made through MCP tools, with ids")
    payment_request_ids: list[int] = Field(default_factory=list)
    purchase_order_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list, description="What stops this from moving, with the tool fact")
    needs_human_approval: bool = False
    recommendation: str = Field(description="Your recommended next step for the Boss")


class BossCall(BaseModel):
    """What the Boss itself writes as its final answer. Deliberately small: the Boss has already
    recorded its decision on the board with update_ticket, and long structured final answers were
    where gpt-6-luna stalled. Everything else is filled in by code (BossDecision)."""

    ticket_id: int
    final_status: TicketStatus = Field(description="The same status you set with update_ticket")
    decision: str = Field(description="The final call in one or two plain sentences")


class BossDecision(BaseModel):
    """The full record of the Boss's call on one ticket: the Boss's own words (BossCall) plus
    what the board and the audit trail show, filled in by code (Team.run_ticket)."""

    ticket_id: int
    decision: str
    final_status: TicketStatus
    rationale: str = Field(description="The Boss's own update_ticket note")
    agents_consulted: list[AgentName] = Field(default_factory=list)
    delegations: list[str] = Field(default_factory=list)
    payment_request_ids: list[int] = Field(default_factory=list)
    purchase_order_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    next_steps_for_human: list[str] = Field(default_factory=list)
    recovered_from_board: bool = Field(
        default=False, description="True if the Boss's final answer never arrived and the call was "
        "taken from the decision it had already recorded with update_ticket")


# ---------------------------------------------------------------------------
# Run dependencies
# ---------------------------------------------------------------------------


@dataclass
class DelegationBudget:
    """Shared across one ticket's whole delegation tree so agents can't loop forever."""

    max_depth: int = 3
    max_delegations: int = 12
    used: int = 0


@dataclass
class TeamDeps:
    """Passed to every agent run. A delegation creates a child copy one level deeper."""

    team: Team
    run_id: str
    agent: AgentName
    ticket_id: int | None = None
    depth: int = 0
    chain: list[AgentName] = field(default_factory=list)
    budget: DelegationBudget = field(default_factory=DelegationBudget)


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

AuditEvent = Literal[
    "run_start",
    "user_prompt",
    "model_request",
    "model_response",
    "run_end",
    "delegation_refused",
    "db_reset",
    "human_decision",
    "ticket_closed",
    "awaiting_human",
    "delegation_failed",
    "boss_output_recovered",
    "boss_decision",
    "error",
]


class AuditEntry(BaseModel):
    """One line of output/audit_trail.json: one step of one agent loop."""

    timestamp: str
    run_id: str = Field(description="One id per ticket run, shared by every agent in its delegation tree")
    ticket_id: int | None
    agent: AgentName | Literal["system", "human"] = Field(
        description="'system' for runner events like a reset; 'human' for approvals from the dashboard"
    )
    parent_agent: AgentName | None = None
    depth: int = 0
    step: int = Field(description="Step number within this agent's loop")
    event: AuditEvent
    model: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
