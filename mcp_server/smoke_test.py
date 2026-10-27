"""Smoke test: connect to the MCP server through .mcp.json, call each tool,
and cross-check every answer against data/campus_customs_new.db.

Writes the evidence to output/mcp_smoke.json.
"""

import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from fastmcp import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.config import load_mcp_config  # noqa: E402
DB_PATH = ROOT / "data" / "campus_customs_new.db"
OUT_PATH = ROOT / "output" / "mcp_smoke.json"

TESTS = [
    {
        "prompt": "Use the campus-customs MCP server to check stock for ticket 101: "
        "SKU CC-TEE-WHITE, size S, quantity needed 1.",
        "tool": "check_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "S", "qty_needed": 1},
        "db_query": "SELECT qty FROM inventory WHERE sku = 'CC-TEE-WHITE' AND size = 'S'",
        "check": lambda out, db: {"on_hand": (out["on_hand"], db[0][0])},
    },
    {
        "prompt": "Use the campus-customs MCP server to check vendor 1's status for "
        "ticket 101 (invoice 501). Will they ship, and what is the lead time?",
        "tool": "check_vendor_status",
        "args": {"vendor_id": 1},
        # Works in any DB state: before payment invoice 501 is open (won't ship); after, it's paid.
        "db_query": "SELECT v.lead_days, "
        "(SELECT group_concat(id) FROM invoices WHERE vendor_id = v.id AND status = 'open'), "
        "(SELECT status FROM invoices WHERE id = 501) FROM vendors v WHERE v.id = 1",
        "check": lambda out, db: {
            "lead_days": (out["vendors"][0]["lead_days"], db[0][0]),
            "open_invoice_ids": (
                [i["invoice_id"] for i in out["vendors"][0]["open_invoices"]],
                [int(x) for x in db[0][1].split(",")] if db[0][1] else [],
            ),
            "will_ship": (out["vendors"][0]["will_ship"], db[0][1] is None),
            "invoice_501_status_in_db": ("paid" if 501 not in [i["invoice_id"] for i in out["vendors"][0]["open_invoices"]] else "open", db[0][2]),
        },
    },
    {
        "prompt": "Use the campus-customs MCP server to check rent for ticket 102 "
        "(lease 1). How much is due, when, and can checking cover it?",
        "tool": "check_rent_due",
        "args": {"lease_id": 1},
        "db_query": "SELECT l.monthly_rent, l.next_due, c.balance FROM leases l, cash_accounts c "
        "WHERE l.id = 1 AND c.name = 'checking'",
        "check": lambda out, db: {
            "monthly_rent": (out["monthly_rent"], db[0][0]),
            "next_due": (out["next_due"], db[0][1]),
            "checking_balance": (out["cash_accounts"][0]["balance"], db[0][2]),
        },
    },
]


async def main() -> None:
    config = load_mcp_config()
    conn = sqlite3.connect(DB_PATH)
    results = []

    async with Client(config) as client:
        listed = sorted(t.name for t in await client.list_tools())
        for test in TESTS:
            response = await client.call_tool(test["tool"], test["args"])
            output = response.structured_content
            db_rows = conn.execute(test["db_query"]).fetchall()
            comparisons = {
                field: {"tool": tool_val, "db": db_val, "match": tool_val == db_val}
                for field, (tool_val, db_val) in test["check"](output, db_rows).items()
            }
            results.append(
                {
                    "prompt": test["prompt"],
                    "tool": test["tool"],
                    "arguments": test["args"],
                    "tool_output": output,
                    "db_check": {
                        "query": test["db_query"],
                        "rows": [list(r) for r in db_rows],
                        "fields": comparisons,
                    },
                    "passed": all(c["match"] for c in comparisons.values()),
                }
            )
    state = conn.execute(
        "SELECT (SELECT qty FROM inventory WHERE sku = 'CC-TEE-WHITE' AND size = 'S'), "
        "(SELECT status FROM invoices WHERE id = 501), (SELECT next_due FROM leases WHERE id = 1), "
        "(SELECT balance FROM cash_accounts WHERE name = 'checking'), (SELECT COUNT(*) FROM payments)"
    ).fetchone()
    conn.close()

    evidence = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_state_checked": {
            "tee_S_on_hand": state[0], "invoice_501_status": state[1], "lease_1_next_due": state[2],
            "checking_balance": state[3], "payments": state[4],
            "note": "Outputs are compared with data/campus_customs_new.db as it is at run time. "
                    "Re-run after a reset and the same checks pass against the original values "
                    "(invoice 501 open, rent due 2026-09-02, checking $3,400).",
        },
        "connection": "stdio via .mcp.json (server: campus-customs)",
        "database": str(DB_PATH.relative_to(ROOT)),
        "tools_listed": listed,
        "all_passed": all(r["passed"] for r in results),
        "tests": results,
    }
    OUT_PATH.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
