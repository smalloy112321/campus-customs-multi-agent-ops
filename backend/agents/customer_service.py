"""Customer Service: drafts messages to customers. Never sees costs, cash or exact stock counts."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="customer_service",
    role="Drafts messages for customers; drafts stay on the board for a human to send.",
    prompt_file="customer_service.md",
    output_type=SpecialistReport,
    mcp_tools=frozenset({"get_shop_today", "get_ticket", "check_availability", "save_draft"}),
)
