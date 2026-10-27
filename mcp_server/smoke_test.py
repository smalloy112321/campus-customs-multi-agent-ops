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
        "db_query": "SELECT v.lead_days, i.id, i.amount, i.due_date, i.status "
        "FROM vendors v JOIN invoices i ON i.vendor_id = v.id WHERE v.id = 1",
        "check": lambda out, db: {
            "lead_days": (out["vendors"][0]["lead_days"], db[0][0]),
            "invoice_id": (out["vendors"][0]["open_invoices"][0]["invoice_id"], db[0][1]),
            "invoice_amount": (out["vendors"][0]["open_invoices"][0]["amount"], db[0][2]),
            "invoice_due_date": (out["vendors"][0]["open_invoices"][0]["due_date"], db[0][3]),
            "will_ship_false_because_open": (out["vendors"][0]["will_ship"], db[0][4] != "open"),
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
    conn.close()

    evidence = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
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
