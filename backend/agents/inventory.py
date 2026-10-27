"""Inventory: checks stock by SKU and size, spots shortfalls, finds the restock vendor."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="inventory",
    role="Checks stock by SKU and size, spots shortfalls, and finds which vendor can restock.",
    prompt_file="inventory.md",
    output_type=SpecialistReport,
    mcp_tools=frozenset({
        "get_shop_today", "get_ticket", "check_stock", "check_availability", "check_vendor_status",
    }),
)
