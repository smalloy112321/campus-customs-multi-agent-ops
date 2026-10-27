"""Run the agent team over the open tickets.

    .venv/bin/python -m backend.run_tickets            # full run: resets the DB first
    .venv/bin/python -m backend.run_tickets --ticket 101 --no-reset

A full run (no --ticket) always resets data/campus_customs_new.db from the
original first, as the shop rules require. Tickets are worked one at a time
because they share one checking account.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from backend import audit
from backend.team import Team
from mcp_server.reset_db import reset_database


async def main(ticket_ids: list[int], reset: bool) -> None:
    if reset:
        result = reset_database()
        audit.log(run_id=f"reset-{uuid.uuid4().hex[:8]}", ticket_id=None, agent="system", step=0,
                  event="db_reset", **result)
        print(f"Reset working database ({result['sha256'][:12]}...)")

    async with Team() as team:
        if not ticket_ids:
            board = await team.call_tool("list_open_tickets")
            ticket_ids = [t["id"] for t in board["tickets"]]
        print(f"Working tickets: {ticket_ids}")
        for ticket_id in ticket_ids:
            decision = await team.run_ticket(ticket_id)
            print(f"\n=== Ticket {ticket_id}: {decision.final_status}")
            print(json.dumps(decision.model_dump(), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticket", type=int, action="append", default=[], help="Ticket id (repeatable)")
    parser.add_argument("--no-reset", action="store_true", help="Skip the reset (only with --ticket)")
    args = parser.parse_args()
    if not args.ticket and args.no_reset:
        parser.error("A full run must start from a reset database; --no-reset needs --ticket.")
    asyncio.run(main(args.ticket, reset=not args.no_reset))
