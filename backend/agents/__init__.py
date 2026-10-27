"""The Campus Customs agent team. Every agent can delegate to every other agent."""

from backend.agents import accounting, boss, customer_service, facilities, inventory
from backend.agents.base import AgentSpec

SPECS: dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (boss.SPEC, inventory.SPEC, accounting.SPEC, facilities.SPEC, customer_service.SPEC)
}
