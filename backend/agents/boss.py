"""The Boss: reads each ticket, routes it to the right specialists, makes the final call."""

from backend.agents.base import AgentSpec
from backend.models import BossDecision

SPEC = AgentSpec(
    name="boss",
    role="Reads each ticket, decides who works on it, verifies their reports, makes the final call.",
    prompt_file="boss.md",
    output_type=BossDecision,
    mcp_tools=frozenset({
        "get_shop_today", "list_open_tickets", "get_ticket", "update_ticket",
        "list_pending_approvals", "check_stock", "check_availability", "check_pricing",
        "check_vendor_status", "check_rent_due", "check_cash",
    }),
)
