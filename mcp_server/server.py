"""Campus Customs MCP server.

Exposes shop data from the working database (data/campus_customs_new.db) as
tools the agent team can call. Every answer comes straight from the database;
nothing is invented. "Today" is always desk.date_today, never the system clock.

Shop rules enforced here (not just in prompts):
- Payment amounts are looked up from the database, never typed in by an agent.
- Agents can only *request* a payment. approve_payment / reject_payment are
  human-only (the backend hides them from every agent, and approve_payment
  refuses an agent name as the approver).
- The pay step refuses if the account would go negative. Cash only goes out.
- No purchase order to a vendor that still has an open invoice.
- Messages are saved as drafts on the board. Nothing is ever sent.
- Customer drafts must use the customer's name and may not reveal shop finances,
  internal dollar figures or exact stock counts.
"""

import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from fastmcp import FastMCP

DB_PATH = Path(
    os.environ.get(
        "CAMPUS_DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db",
    )
)

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = {
    "open",
    "in_progress",
    "waiting_approval",
    "waiting_vendor",
    "resolved",
    "declined",
}
CLOSED_STATUSES = {"resolved", "declined"}
PAYMENT_KINDS = {"invoice", "rent", "purchase_order"}

# Board tables the agents write to. Created on demand in the working copy only;
# a reset (mcp_server/reset_db.py) restores the original file without them.
BOARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_updates (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    agent TEXT NOT NULL,
    status TEXT,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    audience TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    total_cost REAL NOT NULL,
    expected_arrival TEXT NOT NULL,
    ticket_id INTEGER REFERENCES tickets(id),
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_requests (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    payee TEXT NOT NULL,
    amount REAL NOT NULL,
    account TEXT NOT NULL,
    ticket_id INTEGER REFERENCES tickets(id),
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    payment_id INTEGER REFERENCES payments(id)
);
"""

# Words that would leak shop financials into a customer message.
CUSTOMER_BLOCKED_WORDS = [
    "rent", "lease", "landlord", "invoice", "bill", "debt", "owe", "overdue",
    "balance", "cash", "margin", "unit cost", "our cost", "profit", "payment",
    "vendor", "supplier", "checking account", "purchase order",
]
STOCK_COUNT_PATTERN = re.compile(
    r"\b(only\s+\d+|\d+\s+(left|remaining|in stock|on hand|available|units?\s+(left|in stock|available)))\b",
    re.IGNORECASE,
)

mcp = FastMCP("campus-customs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open the working database, make sure the board tables exist, and always close."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # explicit transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(BOARD_SCHEMA)
        yield conn
    finally:
        conn.close()


def _shop_today(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return date.fromisoformat(row["date_today"])


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, days_in_month))


def _open_invoices(conn: sqlite3.Connection, vendor_id: int, today: date) -> list[dict]:
    invoices = []
    for inv in conn.execute(
        "SELECT id, amount, due_date, description FROM invoices "
        "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
        (vendor_id,),
    ):
        days_overdue = (today - date.fromisoformat(inv["due_date"])).days
        invoices.append(
            {
                "invoice_id": inv["id"],
                "amount": inv["amount"],
                "due_date": inv["due_date"],
                "description": inv["description"],
                "days_overdue": max(days_overdue, 0),
                "is_overdue": days_overdue > 0,
            }
        )
    return invoices


def _pending_total(conn: sqlite3.Connection, account: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payment_requests "
        "WHERE status = 'pending' AND account = ?",
        (account,),
    ).fetchone()
    return row["total"]


def _internal_amounts(conn: sqlite3.Connection, ticket: sqlite3.Row) -> set[float]:
    """Dollar figures a customer must never see: costs, rent, invoices, cash, payments."""
    amounts: set[float] = set()
    for sql in (
        "SELECT unit_cost FROM pricing",
        "SELECT monthly_rent FROM leases",
        "SELECT amount FROM invoices",
        "SELECT balance FROM cash_accounts",
        "SELECT amount FROM payments",
        "SELECT amount FROM payment_requests",
        "SELECT total_cost FROM purchase_orders",
    ):
        amounts.update(round(r[0], 2) for r in conn.execute(sql))
    if ticket["sku"] and ticket["qty"]:
        cost = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (ticket["sku"],)).fetchone()
        if cost:
            amounts.add(round(cost["unit_cost"] * ticket["qty"], 2))
    return amounts


def _require_agent(name: str) -> str | None:
    if name not in AGENT_NAMES:
        return f"Unknown agent '{name}'. Use one of: {sorted(AGENT_NAMES)}."
    return None


def _require_ticket(conn: sqlite3.Connection, ticket_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()


# ---------------------------------------------------------------------------
# Read tools: tickets and the shop date
# ---------------------------------------------------------------------------


@mcp.tool
def get_shop_today() -> dict:
    """Return the shop's 'today' (desk.date_today). Use this for every date comparison.

    Reads: desk.
    """
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
    return {"date_today": row["date_today"], "notes": row["notes"]}


@mcp.tool
def list_tickets() -> dict:
    """List every ticket (open or closed) with its status, oldest first.

    Reads: tickets.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM tickets ORDER BY created_at").fetchall()
    tickets = [{**dict(r), "is_resolved": r["status"] in CLOSED_STATUSES} for r in rows]
    return {"count": len(tickets), "tickets": tickets}


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not resolved or declined, oldest first.

    Reads: tickets.
    """
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tickets WHERE status NOT IN ({','.join('?' * len(CLOSED_STATUSES))}) "
            "ORDER BY created_at",
            tuple(CLOSED_STATUSES),
        ).fetchall()
    return {"count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Return one ticket with everything already on the board for it: status updates,
    drafts, purchase orders and payment requests.

    Reads: tickets, ticket_updates, drafts, purchase_orders, payment_requests.
    """
    with _connect() as conn:
        ticket = _require_ticket(conn, ticket_id)
        if ticket is None:
            return {"found": False, "ticket_id": ticket_id, "message": "No such ticket."}
        history = {
            table: [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM {table} WHERE ticket_id = ? ORDER BY id", (ticket_id,)
                )
            ]
            for table in ("ticket_updates", "drafts", "purchase_orders", "payment_requests")
        }
    return {"found": True, "ticket": dict(ticket), **history}


# ---------------------------------------------------------------------------
# Read tools: inventory, pricing, vendors
# ---------------------------------------------------------------------------


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int = 0) -> dict:
    """Check on-hand stock for one SKU and size, and the shortfall against qty_needed.

    Internal use only: the exact count must never be shared with a customer.
    Reads: inventory.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if row is None:
            sizes = [
                r["size"]
                for r in conn.execute("SELECT size FROM inventory WHERE sku = ?", (sku,))
            ]
            return {
                "found": False,
                "sku": sku,
                "size": size,
                "sizes_on_file": sizes,
                "message": "No inventory row for this SKU and size.",
            }

    on_hand = row["qty"]
    return {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "location": row["location"],
        "on_hand": on_hand,
        "qty_needed": qty_needed,
        "shortfall": max(qty_needed - on_hand, 0),
        "can_fill_from_stock": on_hand >= qty_needed,
    }


@mcp.tool
def check_availability(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Customer-safe stock check: says whether the request can be filled from stock,
    without revealing how many units are on hand.

    Reads: inventory.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "size": size, "message": "Not a SKU and size we carry."}
    if row["qty"] >= qty_needed:
        availability = "in_stock"
    elif row["qty"] == 0:
        availability = "out_of_stock"
    else:
        availability = "not_enough_in_stock"
    return {
        "found": True,
        "sku": sku,
        "name": row["name"],
        "size": size,
        "qty_needed": qty_needed,
        "availability": availability,
    }


@mcp.tool
def check_pricing(sku: str, qty: int = 1, discount_pct: float = 0.0) -> dict:
    """Unit cost, list price and margin for a SKU, optionally at a discount off list.

    discount_pct is a percentage (15 means 15% off list). Internal use only.
    Reads: pricing.
    """
    if not 0 <= discount_pct < 100:
        return {"found": False, "message": "discount_pct must be between 0 and 100."}
    with _connect() as conn:
        row = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "message": "No pricing row for this SKU."}

    cost, list_price = row["unit_cost"], row["list_price"]
    unit_price = round(list_price * (1 - discount_pct / 100), 2)
    unit_margin = round(unit_price - cost, 2)
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": cost,
        "list_price": list_price,
        "list_unit_margin": round(list_price - cost, 2),
        "list_margin_pct": round((list_price - cost) / list_price * 100, 1),
        "discount_pct": discount_pct,
        "discounted_unit_price": unit_price,
        "discounted_unit_margin": unit_margin,
        "discounted_margin_pct": round(unit_margin / unit_price * 100, 1) if unit_price else None,
        "order_revenue": round(unit_price * qty, 2),
        "order_cost": round(cost * qty, 2),
        "order_margin": round(unit_margin * qty, 2),
        "breakeven_discount_pct": round((1 - cost / list_price) * 100, 1),
        "sells_below_cost": unit_price < cost,
    }


@mcp.tool
def check_vendor_status(vendor_id: int | None = None) -> dict:
    """List vendors (or one vendor) with lead time and any open invoices.

    A vendor with an open invoice will not ship new product. Overdue means
    due_date is before desk.date_today. Reads: vendors, invoices, desk.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        if vendor_id is None:
            vendors = conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()
        else:
            vendors = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchall()
            if not vendors:
                return {"found": False, "vendor_id": vendor_id, "message": "No such vendor."}

        results = []
        for v in vendors:
            open_invoices = _open_invoices(conn, v["id"], today)
            results.append(
                {
                    "vendor_id": v["id"],
                    "name": v["name"],
                    "specialty": v["specialty"],
                    "lead_days": v["lead_days"],
                    "open_invoices": open_invoices,
                    "open_balance": sum(i["amount"] for i in open_invoices),
                    "will_ship": not open_invoices,
                }
            )

    return {"found": True, "today": today.isoformat(), "vendors": results}


# ---------------------------------------------------------------------------
# Read tools: leases and cash
# ---------------------------------------------------------------------------


@mcp.tool
def check_rent_due(lease_id: int) -> dict:
    """Show a lease's rent, due date, days until due, and whether checking can cover it.

    Reads: leases, cash_accounts, desk.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if lease is None:
            return {"found": False, "lease_id": lease_id, "message": "No such lease."}
        accounts = conn.execute("SELECT name, balance, date FROM cash_accounts").fetchall()

    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    return {
        "found": True,
        "today": today.isoformat(),
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": lease["monthly_rent"],
        "next_due": lease["next_due"],
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
        "cash_accounts": [
            {
                "name": a["name"],
                "balance": a["balance"],
                "can_cover_rent": a["balance"] >= lease["monthly_rent"],
            }
            for a in accounts
        ],
    }


@mcp.tool
def check_cash() -> dict:
    """Cash on hand per account, what is already waiting for approval, and what would be
    left if every pending request were approved. Cash only goes out in this shop.

    Reads: cash_accounts, payment_requests, payments.
    """
    with _connect() as conn:
        accounts = conn.execute("SELECT name, balance, date FROM cash_accounts").fetchall()
        results = []
        for a in accounts:
            pending = _pending_total(conn, a["name"])
            results.append(
                {
                    "name": a["name"],
                    "balance": a["balance"],
                    "as_of": a["date"],
                    "pending_requests_total": pending,
                    "balance_if_all_pending_approved": round(a["balance"] - pending, 2),
                }
            )
        paid = conn.execute("SELECT * FROM payments ORDER BY id").fetchall()
    return {"accounts": results, "payments_made": [dict(p) for p in paid]}


@mcp.tool
def list_pending_approvals() -> dict:
    """Every payment request still waiting for a human decision.

    Reads: payment_requests.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM payment_requests WHERE status = 'pending' ORDER BY id"
        ).fetchall()
    return {"count": len(rows), "pending": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Write tools: the board (ticket updates, drafts)
# ---------------------------------------------------------------------------


@mcp.tool
def update_ticket(ticket_id: int, agent: str, note: str, status: str | None = None) -> dict:
    """Log a note on a ticket and optionally change its status.

    Status must be one of: open, in_progress, waiting_approval, waiting_vendor,
    resolved, declined. The customer's original ticket notes are never overwritten.
    Writes: ticket_updates, tickets.status.
    """
    if err := _require_agent(agent):
        return {"ok": False, "message": err}
    if status is not None and status not in TICKET_STATUSES:
        return {"ok": False, "message": f"Invalid status. Use one of: {sorted(TICKET_STATUSES)}."}
    if not note.strip():
        return {"ok": False, "message": "A note is required."}
    with _connect() as conn:
        if _require_ticket(conn, ticket_id) is None:
            return {"ok": False, "message": f"No ticket {ticket_id}."}
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO ticket_updates (ticket_id, agent, status, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ticket_id, agent, status, note.strip(), _now()),
        )
        if status is not None:
            conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute("COMMIT")
        ticket = conn.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return {"ok": True, "update_id": cur.lastrowid, "ticket_id": ticket_id, "status": ticket["status"]}


@mcp.tool
def save_draft(
    ticket_id: int, audience: str, recipient: str, subject: str, body: str, author: str
) -> dict:
    """Save a message draft on the board. Nothing is ever sent; a human reviews drafts.

    audience is 'customer', 'vendor', 'landlord' or 'internal'. Customer drafts must use
    the requester's name from the ticket and may not mention shop finances (rent, bills,
    invoices, cash, costs, margins, vendors) or exact stock counts. A customer's own price
    may be quoted; internal dollar figures may not. Writes: drafts.
    """
    if err := _require_agent(author):
        return {"ok": False, "message": err}
    if audience not in {"customer", "vendor", "landlord", "internal"}:
        return {"ok": False, "message": "audience must be customer, vendor, landlord or internal."}
    if not body.strip() or not subject.strip():
        return {"ok": False, "message": "subject and body are required."}

    with _connect() as conn:
        ticket = _require_ticket(conn, ticket_id)
        if ticket is None:
            return {"ok": False, "message": f"No ticket {ticket_id}."}

        if audience == "customer":
            problems = []
            requester = ticket["requester"]
            if recipient.strip().lower() != requester.lower():
                problems.append(f"recipient must be the requester on the ticket: '{requester}'.")
            first_name = requester.split()[0]
            if first_name.lower() not in body.lower():
                problems.append(f"address the customer by name (include '{first_name}').")
            text = f"{subject}\n{body}".lower()
            leaked = [w for w in CUSTOMER_BLOCKED_WORDS if re.search(rf"\b{re.escape(w)}", text)]
            internal = _internal_amounts(conn, ticket)
            for amount in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", text):
                if round(float(amount.replace(",", "")), 2) in internal:
                    leaked.append(f"${amount} (internal figure)")
            if leaked:
                problems.append(f"remove shop-financial terms: {leaked}.")
            if STOCK_COUNT_PATTERN.search(text):
                problems.append("do not state how many units are in stock; say in stock or out of stock.")
            if problems:
                return {"ok": False, "message": "Draft refused: " + " ".join(problems)}

        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, audience, recipient, subject, body, author, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, audience, recipient.strip(), subject.strip(), body.strip(), author, _now()),
        )
    return {"ok": True, "draft_id": cur.lastrowid, "status": "draft", "sent": False}


# ---------------------------------------------------------------------------
# Write tools: money (requests only; humans decide)
# ---------------------------------------------------------------------------


@mcp.tool
def create_purchase_order(
    vendor_id: int, sku: str, size: str, qty: int, requested_by: str, ticket_id: int | None = None
) -> dict:
    """Draft a restock purchase order and queue its payment for human approval.

    Refused if the vendor still has an open invoice (they will not ship). Cost comes
    from pricing.unit_cost; expected arrival is desk.date_today + vendors.lead_days.
    Reads: vendors, invoices, inventory, pricing, desk. Writes: purchase_orders, payment_requests.
    """
    if err := _require_agent(requested_by):
        return {"ok": False, "message": err}
    if qty <= 0:
        return {"ok": False, "message": "qty must be positive."}
    with _connect() as conn:
        today = _shop_today(conn)
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"ok": False, "message": f"No vendor {vendor_id}."}
        if conn.execute(
            "SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone() is None:
            return {"ok": False, "message": f"{sku} size {size} is not an item we carry."}
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return {"ok": False, "message": f"No pricing row for {sku}."}
        if ticket_id is not None and _require_ticket(conn, ticket_id) is None:
            return {"ok": False, "message": f"No ticket {ticket_id}."}

        blocking = _open_invoices(conn, vendor_id, today)
        if blocking:
            return {
                "ok": False,
                "refused": True,
                "message": f"{vendor['name']} has an open invoice and will not ship new product.",
                "blocking_invoices": blocking,
            }

        total = round(price["unit_cost"] * qty, 2)
        arrival = date.fromordinal(today.toordinal() + vendor["lead_days"]).isoformat()
        conn.execute("BEGIN IMMEDIATE")
        po = conn.execute(
            "INSERT INTO purchase_orders (vendor_id, sku, size, qty, unit_cost, total_cost, "
            "expected_arrival, ticket_id, requested_by, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?)",
            (vendor_id, sku, size, qty, price["unit_cost"], total, arrival, ticket_id,
             requested_by, _now()),
        )
        req = conn.execute(
            "INSERT INTO payment_requests (kind, ref_id, payee, amount, account, ticket_id, "
            "requested_by, reason, created_at) VALUES ('purchase_order', ?, ?, ?, 'checking', ?, ?, ?, ?)",
            (po.lastrowid, vendor["name"], total, ticket_id, requested_by,
             f"Restock {qty} x {sku} size {size}", _now()),
        )
        conn.execute("COMMIT")
        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()
        pending = _pending_total(conn, "checking")
    return {
        "ok": True,
        "purchase_order_id": po.lastrowid,
        "payment_request_id": req.lastrowid,
        "vendor": vendor["name"],
        "total_cost": total,
        "expected_arrival": arrival,
        "status": "pending_approval",
        "checking_balance": balance["balance"],
        "pending_requests_total": pending,
        "balance_if_all_pending_approved": round(balance["balance"] - pending, 2),
    }


@mcp.tool
def request_payment(kind: str, ref_id: int, requested_by: str, reason: str, ticket_id: int | None = None) -> dict:
    """Queue a payment for human approval. Nothing is paid until a human approves it.

    kind is 'invoice' (ref_id = invoices.id), 'rent' (ref_id = leases.id) or
    'purchase_order' (ref_id = purchase_orders.id). The amount is looked up from the
    database. Reads: invoices, leases, purchase_orders, vendors, cash_accounts.
    Writes: payment_requests.
    """
    if err := _require_agent(requested_by):
        return {"ok": False, "message": err}
    if kind not in PAYMENT_KINDS:
        return {"ok": False, "message": f"kind must be one of {sorted(PAYMENT_KINDS)}."}
    if not reason.strip():
        return {"ok": False, "message": "A reason is required."}

    with _connect() as conn:
        if ticket_id is not None and _require_ticket(conn, ticket_id) is None:
            return {"ok": False, "message": f"No ticket {ticket_id}."}
        if kind == "invoice":
            target = conn.execute(
                "SELECT i.amount, i.status, v.name AS payee FROM invoices i "
                "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (ref_id,)
            ).fetchone()
            if target is None or target["status"] != "open":
                return {"ok": False, "message": f"Invoice {ref_id} not found or not open."}
        elif kind == "rent":
            target = conn.execute(
                "SELECT monthly_rent AS amount, landlord AS payee FROM leases WHERE id = ?", (ref_id,)
            ).fetchone()
            if target is None:
                return {"ok": False, "message": f"No lease {ref_id}."}
        else:
            target = conn.execute(
                "SELECT p.total_cost AS amount, p.status, v.name AS payee FROM purchase_orders p "
                "JOIN vendors v ON v.id = p.vendor_id WHERE p.id = ?", (ref_id,)
            ).fetchone()
            if target is None or target["status"] != "pending_approval":
                return {"ok": False, "message": f"Purchase order {ref_id} not found or not awaiting approval."}

        duplicate = conn.execute(
            "SELECT id FROM payment_requests WHERE kind = ? AND ref_id = ? AND status = 'pending'",
            (kind, ref_id),
        ).fetchone()
        if duplicate:
            return {"ok": False, "message": f"Already pending as request {duplicate['id']}.",
                    "payment_request_id": duplicate["id"]}

        cur = conn.execute(
            "INSERT INTO payment_requests (kind, ref_id, payee, amount, account, ticket_id, "
            "requested_by, reason, created_at) VALUES (?, ?, ?, ?, 'checking', ?, ?, ?, ?)",
            (kind, ref_id, target["payee"], target["amount"], ticket_id, requested_by,
             reason.strip(), _now()),
        )
        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()
        pending = _pending_total(conn, "checking")
    return {
        "ok": True,
        "payment_request_id": cur.lastrowid,
        "status": "pending",
        "kind": kind,
        "ref_id": ref_id,
        "payee": target["payee"],
        "amount": target["amount"],
        "checking_balance": balance["balance"],
        "pending_requests_total": pending,
        "balance_if_all_pending_approved": round(balance["balance"] - pending, 2),
        "message": "Waiting for human approval. Nothing has been paid.",
    }


# ---------------------------------------------------------------------------
# Human-only tools (hidden from every agent; called by the dashboard)
# ---------------------------------------------------------------------------


def _resolve_if_last_payment(conn: sqlite3.Connection, req: sqlite3.Row, payment_id: int, approver: str) -> bool:
    """Inside the approval transaction: if the ticket behind this request has no other
    pending payment, mark it resolved and log who did it. Returns True if resolved."""
    ticket_id = req["ticket_id"]
    if ticket_id is None:
        return False
    ticket = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket is None or ticket["status"] in CLOSED_STATUSES:
        return False
    still_pending = conn.execute(
        "SELECT COUNT(*) AS n FROM payment_requests WHERE ticket_id = ? AND status = 'pending'", (ticket_id,)
    ).fetchone()["n"]
    if still_pending:
        return False
    conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
    conn.execute(
        "INSERT INTO ticket_updates (ticket_id, agent, status, note, created_at) VALUES (?, 'human', 'resolved', ?, ?)",
        (ticket_id,
         f"{approver} approved payment request {req['id']} (${req['amount']:,.2f} {req['kind']} to "
         f"{req['payee']}, payment {payment_id}). No payments left pending on this ticket, so it is resolved.",
         _now()),
    )
    return True


@mcp.tool
def approve_payment(request_id: int, approved_by: str, note: str = "") -> dict:
    """HUMAN ONLY. Approve a pending payment request and pay it.

    Refuses if the account would go negative. On success: inserts into payments,
    lowers cash_accounts.balance, and marks the invoice paid, moves the lease's
    next_due forward one month, or marks the purchase order ordered. If this was the
    last pending payment on its ticket, the ticket is marked resolved and the change
    is logged in ticket_updates as a human update.
    Writes: payment_requests, payments, cash_accounts, invoices | leases | purchase_orders,
    tickets.status, ticket_updates.
    """
    if not approved_by.strip() or approved_by.strip().lower() in AGENT_NAMES:
        return {"ok": False, "message": "approved_by must be a named human, not an agent."}

    with _connect() as conn:
        today = _shop_today(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
            if req is None or req["status"] != "pending":
                conn.execute("ROLLBACK")
                return {"ok": False, "message": f"Request {request_id} not found or not pending."}

            account = conn.execute(
                "SELECT balance FROM cash_accounts WHERE name = ?", (req["account"],)
            ).fetchone()
            if account is None:
                conn.execute("ROLLBACK")
                return {"ok": False, "message": f"No cash account '{req['account']}'."}
            if account["balance"] - req["amount"] < 0:
                conn.execute("ROLLBACK")
                return {
                    "ok": False,
                    "refused": True,
                    "message": "Not enough cash. Payment refused; balance would go negative.",
                    "balance": account["balance"],
                    "amount": req["amount"],
                }

            # Re-check the target is still payable and update it.
            if req["kind"] == "invoice":
                inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
                if inv is None or inv["status"] != "open":
                    conn.execute("ROLLBACK")
                    return {"ok": False, "message": f"Invoice {req['ref_id']} is no longer open."}
                conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
                target_update = {"table": "invoices", "id": req["ref_id"], "status": "paid"}
            elif req["kind"] == "rent":
                lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
                new_due = _add_month(date.fromisoformat(lease["next_due"])).isoformat()
                conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, req["ref_id"]))
                target_update = {"table": "leases", "id": req["ref_id"],
                                 "previous_next_due": lease["next_due"], "next_due": new_due}
            else:
                po = conn.execute(
                    "SELECT p.status, p.vendor_id FROM purchase_orders p WHERE p.id = ?", (req["ref_id"],)
                ).fetchone()
                if po is None or po["status"] != "pending_approval":
                    conn.execute("ROLLBACK")
                    return {"ok": False, "message": f"Purchase order {req['ref_id']} is not awaiting approval."}
                if _open_invoices(conn, po["vendor_id"], today):
                    conn.execute("ROLLBACK")
                    return {"ok": False, "refused": True,
                            "message": "Vendor has an open invoice and will not ship; pay that first."}
                conn.execute("UPDATE purchase_orders SET status = 'ordered' WHERE id = ?", (req["ref_id"],))
                target_update = {"table": "purchase_orders", "id": req["ref_id"], "status": "ordered"}

            new_balance = round(account["balance"] - req["amount"], 2)
            pay = conn.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (req["kind"], req["ref_id"], req["amount"], req["account"], today.isoformat(),
                 approved_by.strip()),
            )
            conn.execute(
                "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                (new_balance, today.isoformat(), req["account"]),
            )
            conn.execute(
                "UPDATE payment_requests SET status = 'approved', decided_by = ?, decided_at = ?, "
                "decision_note = ?, payment_id = ? WHERE id = ?",
                (approved_by.strip(), _now(), note, pay.lastrowid, request_id),
            )
            ticket_resolved = _resolve_if_last_payment(conn, req, pay.lastrowid, approved_by.strip())
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return {
        "ok": True,
        "payment_id": pay.lastrowid,
        "request_id": request_id,
        "amount": req["amount"],
        "account": req["account"],
        "new_balance": new_balance,
        "paid_at": today.isoformat(),
        "approved_by": approved_by.strip(),
        "updated": target_update,
        "ticket_id": req["ticket_id"],
        "ticket_resolved": ticket_resolved,
    }


@mcp.tool
def resolve_ticket_after_run(ticket_id: int, note: str = "") -> dict:
    """SYSTEM ONLY (hidden from agents). Called when an agent run on a ticket finishes.

    Marks the ticket resolved unless a payment for it is still waiting for a human; in
    that case it stays open until the last payment is approved (see approve_payment).
    Writes: tickets.status, ticket_updates (agent 'system').
    """
    with _connect() as conn:
        ticket = _require_ticket(conn, ticket_id)
        if ticket is None:
            return {"ok": False, "message": f"No ticket {ticket_id}."}
        if ticket["status"] in CLOSED_STATUSES:
            return {"ok": True, "ticket_id": ticket_id, "resolved": True, "status": ticket["status"],
                    "message": "Already closed."}
        pending = conn.execute(
            "SELECT id, amount, payee FROM payment_requests WHERE ticket_id = ? AND status = 'pending'",
            (ticket_id,),
        ).fetchall()
        if pending:
            return {"ok": True, "ticket_id": ticket_id, "resolved": False, "status": ticket["status"],
                    "waiting_on_human": [dict(p) for p in pending],
                    "message": "Waiting for a human to approve or reject pending payments."}
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
        conn.execute(
            "INSERT INTO ticket_updates (ticket_id, agent, status, note, created_at) VALUES (?, 'system', 'resolved', ?, ?)",
            (ticket_id, ("Agent run finished with nothing waiting for a human approval. " + note).strip(), _now()),
        )
        conn.execute("COMMIT")
    return {"ok": True, "ticket_id": ticket_id, "resolved": True, "status": "resolved"}


@mcp.tool
def reject_payment(request_id: int, rejected_by: str, note: str = "") -> dict:
    """HUMAN ONLY. Reject a pending payment request. No money moves.

    Writes: payment_requests (and purchase_orders.status for a rejected PO).
    """
    if not rejected_by.strip() or rejected_by.strip().lower() in AGENT_NAMES:
        return {"ok": False, "message": "rejected_by must be a named human, not an agent."}
    with _connect() as conn:
        req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None or req["status"] != "pending":
            return {"ok": False, "message": f"Request {request_id} not found or not pending."}
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE payment_requests SET status = 'rejected', decided_by = ?, decided_at = ?, "
            "decision_note = ? WHERE id = ?",
            (rejected_by.strip(), _now(), note, request_id),
        )
        if req["kind"] == "purchase_order":
            conn.execute("UPDATE purchase_orders SET status = 'rejected' WHERE id = ?", (req["ref_id"],))
        conn.execute("COMMIT")
    return {"ok": True, "request_id": request_id, "status": "rejected", "ticket_id": req["ticket_id"]}


if __name__ == "__main__":
    mcp.run(show_banner=False)
