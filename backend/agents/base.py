"""Shared building blocks for every agent: the spec each agent file declares, the
MCP tool filter, and the `delegate` tool that gives the team full connectivity."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from backend import audit
from backend.config import PROMPTS_DIR, REQUEST_TIMEOUT_SECONDS
from backend.models import AGENT_NAMES, AgentName, TeamDeps

# Model-side failures (timeouts after every retry, API errors, unusable output). A usage limit is
# NOT in this list: hitting a budget should stop the ticket.
MODEL_FAILURES = (FallbackExceptionGroup, ModelAPIError, UnexpectedModelBehavior)

# MCP tools only a human (dashboard) or the runner may call. No agent ever sees them.
HUMAN_ONLY_TOOLS = frozenset({"approve_payment", "reject_payment", "resolve_ticket_after_run"})


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    role: str
    prompt_file: str
    output_type: type
    mcp_tools: frozenset[str]

    def __post_init__(self) -> None:
        if leaked := self.mcp_tools & HUMAN_ONLY_TOOLS:
            raise ValueError(f"{self.name} may not be given human-only tools: {sorted(leaked)}")

    def load_prompt(self) -> str:
        return (PROMPTS_DIR / self.prompt_file).read_text()


async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> str:
    """Hand a self-contained task to a teammate and get their report back.

    to: boss, inventory, accounting, facilities or customer_service (not yourself).
    task: everything they need: ticket id, SKU/size/qty, invoice or lease ids,
    and exactly what you want back. They cannot see your conversation.
    """
    deps = ctx.deps
    budget = deps.budget
    reason = None
    if to not in AGENT_NAMES:
        reason = f"Unknown teammate '{to}'. Choose from {list(AGENT_NAMES)}."
    elif to == deps.agent:
        reason = "You cannot delegate to yourself."
    elif deps.depth + 1 > budget.max_depth:
        reason = f"Delegation chain is already {deps.depth} deep ({' -> '.join(deps.chain + [deps.agent])}). Finish with what you have."
    elif budget.used >= budget.max_delegations:
        reason = f"This ticket has used all {budget.max_delegations} delegations. Finish with what you have."
    if reason:
        audit.log(run_id=deps.run_id, ticket_id=deps.ticket_id, agent=deps.agent, step=ctx.run_step,
                  event="delegation_refused", depth=deps.depth, to=to, task=task, reason=reason)
        return f"DELEGATION REFUSED: {reason}"

    budget.used += 1
    try:
        output = await deps.team.run_agent(
            to,
            task,
            run_id=deps.run_id,
            ticket_id=deps.ticket_id,
            parent=deps.agent,
            depth=deps.depth + 1,
            chain=deps.chain + [deps.agent],
            budget=budget,
            usage=ctx.usage,
        )
    except MODEL_FAILURES as exc:
        # A teammate that can't get an answer from the model shouldn't strand the whole ticket.
        audit.log(run_id=deps.run_id, ticket_id=deps.ticket_id, agent=deps.agent, step=ctx.run_step,
                  event="delegation_failed", depth=deps.depth, to=to, error=f"{type(exc).__name__}: {exc}")
        return (f"DELEGATION FAILED: {to} could not finish ({type(exc).__name__}). Check the board with "
                "get_ticket for anything it already recorded, and decide with what you have.")
    return output.model_dump_json()


def build_agent(spec: AgentSpec, model: Model, mcp: MCPToolset) -> Agent[TeamDeps, object]:
    """One PydanticAI agent: its own prompt, its slice of the MCP tools, and `delegate`."""
    allowed = spec.mcp_tools
    return Agent(
        model,
        name=spec.name,
        instructions=spec.load_prompt(),
        deps_type=TeamDeps,
        output_type=spec.output_type,
        toolsets=[mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)],
        tools=[delegate],
        retries=2,
        model_settings={"request_timeout": REQUEST_TIMEOUT_SECONDS},
    )
