"""Facilities: handles the shop side: the lease, rent, and the landlord."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="facilities",
    role="Handles the shop side: leases, rent and the landlord.",
    prompt_file="facilities.md",
    output_type=SpecialistReport,
    mcp_tools=frozenset({
        "get_shop_today", "get_ticket", "check_rent_due", "list_pending_approvals", "save_draft",
    }),
)
