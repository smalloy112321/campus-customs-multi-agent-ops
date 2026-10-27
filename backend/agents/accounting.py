"""Accounting: watches cash and invoices, checks margins, queues payments and POs for approval."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="accounting",
    role="Watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval.",
    prompt_file="accounting.md",
    output_type=SpecialistReport,
    mcp_tools=frozenset({
        "get_shop_today", "get_ticket", "check_cash", "list_pending_approvals",
        "check_vendor_status", "check_rent_due", "check_pricing", "check_stock",
        "request_payment", "create_purchase_order",
    }),
)
