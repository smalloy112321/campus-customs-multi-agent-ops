"""Build the Problem 9 deliverables from the real run.

Reads only the record of what happened:
  - output/audit_trail.json  (every agent-loop step; only runs after the last db_reset)
  - data/campus_customs_new.db (opened read-only: tickets, payments, cash, board tables)
  - data/campus_customs.db     (original; the starting balance a reset restores)
and writes:
  - output/resolved_tickets.json
  - the "ticket-actuals" JSON block inside output/desk_tickets.html (Actual sections + Cash tab)
  - output/resolved_board.html  (board screenshots from output/screenshots/, embedded)

The cash ledger is recomputed from the payments table and must equal cash_accounts;
the script stops without writing anything if it doesn't.

    .venv/bin/python scripts/build_problem9_report.py
"""

from __future__ import annotations

import base64
import html
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.efficiency import measure  # noqa: E402

OUT = ROOT / "output"
AUDIT = OUT / "audit_trail.json"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
DESK = OUT / "desk_tickets.html"
SHOTS = OUT / "screenshots"
TICKETS = (101, 102, 103)
LABEL = {"boss": "The Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service"}
SPECIALISTS = ["inventory", "accounting", "facilities", "customer_service"]
KIND = {"invoice": "Vendor invoice", "rent": "Rent", "purchase_order": "Purchase order"}


def ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows(conn: sqlite3.Connection, sql: str, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def entries_since_reset() -> tuple[list[dict], dict]:
    entries = json.loads(AUDIT.read_text())
    i = max(i for i, e in enumerate(entries) if e["event"] == "db_reset")
    return entries[i + 1:], entries[i]


def run_for(ticket_id: int, entries: list[dict]) -> list[dict]:
    mine = [e for e in entries if e.get("ticket_id") == ticket_id and str(e["run_id"]).startswith(f"ticket-{ticket_id}-")]
    if not mine:
        raise SystemExit(f"No run for ticket {ticket_id} since the last reset; run all three tickets first.")
    run_id = mine[-1]["run_id"]
    return [e for e in mine if e["run_id"] == run_id]


def describe_run(ticket_id: int, run: list[dict], since_reset: list[dict]) -> dict:
    delegations, tools = [], {}
    models = set()
    for e in run:
        if e["event"] != "model_response":
            continue
        models.add(e["model"])
        for p in e["detail"]["parts"]:
            if p.get("kind") != "tool-call" or p["tool_name"] == "final_result":
                continue
            if p["tool_name"] == "delegate":
                delegations.append({"from": e["agent"], "to": p["args"].get("to"), "task": p["args"].get("task", "")})
            else:
                tools.setdefault(e["agent"], Counter())[p["tool_name"]] += 1

    contributions, worked = [], []
    for e in run:
        if e["event"] != "run_end":
            continue
        out = e["detail"]["output"]
        worked.append(e["agent"])
        contributions.append({
            "agent": e["agent"],
            "called_by": e.get("parent_agent"),
            "contribution": out.get("decision") if e["agent"] == "boss" else out.get("summary"),
        })
    contributions.sort(key=lambda c: c["agent"] != "boss")  # Boss first, then in run order
    boss_out = next(e["detail"]["output"] for e in reversed(run) if e["event"] == "run_end" and e["agent"] == "boss")
    order = ["boss", *SPECIALISTS]
    eff = measure(ticket_id, since_reset)
    return {
        "run_id": run[0]["run_id"],
        "started_at": run[0]["timestamp"],
        "finished_at": next(e["timestamp"] for e in reversed(run) if e["event"] == "run_end" and e["agent"] == "boss"),
        "models": sorted(models),
        "first_called": delegations[0]["to"] if delegations and delegations[0]["from"] == "boss" else None,
        "specialists": [a for a in SPECIALISTS if a in worked],
        "not_called": [a for a in SPECIALISTS if a not in worked],
        "delegations": delegations,
        "tools_by_agent": [
            {"agent": a, "total": sum(tools[a].values()),
             "tools": [{"tool": t, "count": n} for t, n in tools[a].items()]}
            for a in order if a in tools
        ],
        "contributions": contributions,
        "boss_final_status": boss_out["final_status"],
        "boss_decision": boss_out["decision"],
        "efficiency": {k: eff[k] for k in ("score", "rating", "specialists", "delegations", "mcp_tool_calls",
                                           "model_requests", "budget", "missing_required_tools",
                                           "unexpected_tool_calls", "repeated_calls", "penalties", "improvements")},
    }


def main() -> None:
    since_reset, reset_event = entries_since_reset()
    db = ro(WORKING_DB)
    original = ro(ORIGINAL_DB)

    # ---- Cash: start (what a reset restores), ledger from payments, end from cash_accounts.
    start = original.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
    db_balance = db.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
    payments = rows(db, """
        SELECT p.id AS payment_id, p.kind, p.ref_id, p.amount, p.account, p.paid_at, p.approved_by,
               r.id AS request_id, r.ticket_id, r.payee, r.decided_at, r.requested_by, r.decision_note
        FROM payments p JOIN payment_requests r ON r.payment_id = p.id
        WHERE p.account = 'checking' ORDER BY p.id""")
    balance, lowest, ledger = start, start, []
    for p in payments:
        balance = round(balance - p["amount"], 2)
        lowest = min(lowest, balance)
        ref = f"invoice {p['ref_id']}" if p["kind"] == "invoice" else f"lease {p['ref_id']}" if p["kind"] == "rent" else f"PO {p['ref_id']}"
        ledger.append({**p, "what": f"{KIND[p['kind']]} ({ref}) to {p['payee']}, request #{p['request_id']}",
                       "approved_at": p["decided_at"], "balance_after": balance})
    if round(balance, 2) != round(db_balance, 2):
        raise SystemExit(f"Cash mismatch: ledger ends at {balance}, cash_accounts says {db_balance}. Nothing written.")
    if lowest < 0:
        raise SystemExit("A balance went negative; the pay tool should have refused. Nothing written.")

    # ---- Tickets.
    tickets_out, actuals, by_ticket = [], {}, []
    for tid in TICKETS:
        t = db.execute("SELECT * FROM tickets WHERE id = ?", (tid,)).fetchone()
        if t["status"] != "resolved":
            raise SystemExit(f"Ticket {tid} is {t['status']}, not resolved. Finish the run first.")
        run = describe_run(tid, run_for(tid, since_reset), since_reset)
        resolved = db.execute("SELECT agent, note, created_at FROM ticket_updates WHERE ticket_id = ? AND status = 'resolved' "
                              "ORDER BY id DESC LIMIT 1", (tid,)).fetchone()
        approvals = rows(db, "SELECT id AS request_id, kind, ref_id, payee, amount, requested_by, status, decided_by, "
                             "decided_at, payment_id, decision_note FROM payment_requests WHERE ticket_id = ? ORDER BY id", tid)
        drafts = rows(db, "SELECT id, audience, recipient, subject, author, status FROM drafts WHERE ticket_id = ? ORDER BY id", tid)
        pos = rows(db, "SELECT id, vendor_id, sku, size, qty, total_cost, status FROM purchase_orders WHERE ticket_id = ?", tid)
        paid = [l for l in ledger if l["ticket_id"] == tid]
        change = -round(sum(l["amount"] for l in paid), 2)
        if resolved["agent"] == "human":
            who = ", ".join(sorted({a["decided_by"] for a in approvals if a["status"] == "approved"}))
            resolved_by = f"Human approval by {who} ({', '.join(f'request #{a['request_id']}' for a in approvals if a['status'] == 'approved')})"
        else:
            resolved_by = "Run finished with nothing waiting for a human (no payment needed)"
        items = "; ".join(f"{KIND[l['kind']]} to {l['payee']}: ${l['amount']:,.2f} (payment #{l['payment_id']})" for l in paid) \
            or "No pay or purchase. Restock vendor blocked, so no purchase order was queued."
        outcome = f"{run['boss_decision']} Resolved: {resolved_by.lower() if resolved['agent'] != 'human' else resolved_by}."

        actuals[str(tid)] = {**run, "outcome": outcome, "resolved_by": resolved_by, "cash_change": change}
        by_ticket.append({"ticket_id": tid, "subject": t["subject"], "resolved_by": resolved_by,
                          "resolved_at": resolved["created_at"], "items": items, "cash_change": change})
        tickets_out.append({
            "id": tid,
            "subject": t["subject"],
            "type": t["type"],
            "requester": t["requester"],
            "final_status": t["status"],
            "boss_final_call": run["boss_final_status"],
            "resolved_by": resolved_by,
            "resolved_at": resolved["created_at"],
            "short_outcome": outcome,
            "agents": [{"agent": c["agent"], "called_by": c["called_by"], "contribution": c["contribution"]}
                       for c in run["contributions"]],
            "not_called": run["not_called"],
            "delegations": [{"from": d["from"], "to": d["to"]} for d in run["delegations"]],
            "human_approvals": [a for a in approvals if a["decided_by"]],
            "cash_change": change,
            "drafts": [{**d, "sent": False} for d in drafts],
            "purchase_orders": pos,
            "efficiency": {k: run["efficiency"][k] for k in ("score", "rating", "penalties")},
            "run_id": run["run_id"],
        })

    total = round(sum(b["cash_change"] for b in by_ticket), 2)
    assert round(start + total, 2) == round(db_balance, 2)
    cash = {
        "reset_at": reset_event["timestamp"],
        "starting_balance": start,
        "ledger": ledger,
        "by_ticket": by_ticket,
        "total_change": total,
        "ending_balance": round(start + total, 2),
        "db_balance": db_balance,
        "matches": True,
        "lowest_balance": lowest,
        "notes": [
            "Order matters: the overdue invoice (#1) was approved before the rent (#2), as the Boss and Accounting advised.",
            "Ticket 103 moved no money: Bulldog Print Co was still blocked by invoice 501 during its run, and a 12-hoodie "
            "restock ($264) would not fit in the $160 left after both approvals anyway.",
            "Payments are dated with the shop's today (desk.date_today = 2026-08-31); approval times are real clock times.",
        ],
    }

    # ---- Write resolved_tickets.json.
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reset_at": reset_event["timestamp"],
        "starting_balance": start,
        "ending_balance": db_balance,
        "cash_matches_database": True,
        "tickets": tickets_out,
    }
    (OUT / "resolved_tickets.json").write_text(json.dumps(report, indent=2) + "\n")

    # ---- Fill the actuals block in desk_tickets.html.
    page = DESK.read_text()
    block = json.dumps({"tickets": actuals, "cash": cash}, indent=1).replace("</", "<\\/")
    page, n = re.subn(r'(<script type="application/json" id="ticket-actuals">).*?(</script>)',
                      lambda m: m.group(1) + block + m.group(2), page, count=1, flags=re.DOTALL)
    assert n == 1, "ticket-actuals block not found in desk_tickets.html"
    DESK.write_text(page)

    # ---- resolved_board.html with the screenshots embedded (opens by double-click).
    write_board(tickets_out, cash)
    print(f"Start ${start:,.2f} -> end ${db_balance:,.2f} (cash_accounts ${db_balance:,.2f}) OK")
    for t in tickets_out:
        print(f"  {t['id']}: {t['final_status']}, cash {t['cash_change']:+,.2f}, efficiency {t['efficiency']['score']}")


def write_board(tickets: list[dict], cash: dict) -> None:
    esc = html.escape
    sections = []
    for t in tickets:
        shot = SHOTS / f"ticket-{t['id']}.png"
        img = base64.b64encode(shot.read_bytes()).decode()
        after = next((l["balance_after"] for l in reversed(cash["ledger"]) if l["ticket_id"] == t["id"]), None)
        sections.append(f"""
  <section id="t{t['id']}" class="card">
    <h2>Ticket {t['id']}: {esc(t['subject'])} <span class="pill">Resolved</span> <span class="pill score">⚡ {t['efficiency']['score']} · {t['efficiency']['rating']}</span></h2>
    <p class="meta">{esc(t['requester'])} · {esc(t['resolved_by'])} · cash change <b>{'−' if t['cash_change'] else ''}${abs(t['cash_change']):,.2f}</b>{f' (checking after: ${after:,.2f})' if after is not None else ''}</p>
    <p>{esc(t['short_outcome'])}</p>
    <img src="data:image/png;base64,{img}" alt="Screenshot of the React operations board with ticket {t['id']} selected and resolved">
  </section>""")
    nav = " · ".join(f'<a href="#t{t["id"]}">Ticket {t["id"]}</a>' for t in tickets)
    (OUT / "resolved_board.html").write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs: Resolved Board</title>
<style>
  body {{ margin: 0; font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1d2733; background: #f5f7fa; }}
  header {{ background: #00356b; color: #fff; padding: 22px 28px; }}
  header h1 {{ margin: 0; font-family: Georgia, serif; font-size: 26px; }}
  header p {{ margin: 6px 0 0; color: #d6e2f0; }}
  header a {{ color: #fff; }}
  main {{ max-width: 1240px; margin: 0 auto; padding: 24px 28px 60px; }}
  .card {{ background: #fff; border: 1px solid #d9dee5; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }}
  h2 {{ margin: 0 0 6px; font-family: Georgia, serif; color: #00356b; }}
  .pill {{ display: inline-block; font: 600 12px/1 -apple-system, sans-serif; padding: 4px 10px; border-radius: 999px; background: #e3f4e8; color: #1e6b3a; vertical-align: middle; }}
  .pill.score {{ background: #e8eef6; color: #00356b; }}
  .meta {{ color: #55606e; margin: 0 0 6px; }}
  .totals {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }}
  .totals div {{ background: rgb(255 255 255 / 12%); border: 1px solid rgb(255 255 255 / 25%); border-radius: 8px; padding: 6px 14px; }}
  img {{ width: 100%; border: 1px solid #d9dee5; border-radius: 8px; margin-top: 10px; }}
</style>
</head>
<body>
<header>
  <h1>Campus Customs Operations Desk: resolved board</h1>
  <p>Full run after a reset · screenshots of the React board (localhost:5173), one per resolved ticket · {nav}</p>
  <div class="totals">
    <div>Starting checking <b>${cash['starting_balance']:,.2f}</b></div>
    <div>Paid out <b>${-cash['total_change']:,.2f}</b></div>
    <div>Ending checking <b>${cash['ending_balance']:,.2f}</b> (matches <code>cash_accounts</code>)</div>
  </div>
</header>
<main>{''.join(sections)}
</main>
</body>
</html>
""")


if __name__ == "__main__":
    main()
