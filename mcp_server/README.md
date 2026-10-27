# Campus Customs MCP Server

This server gives the agent team (Boss, Inventory, Accounting, Facilities, Customer Service) one shared, rule-checked way to read and update shop data, so agents never query the database directly. It's built with [FastMCP](https://gofastmcp.com).

## Database

- **Uses:** `../data/campus_customs_new.db`, the working copy that every tool reads from and writes to.
- **Never touches:** `../data/campus_customs.db`, the original snapshot kept for resets.
- "Today" always comes from `desk.date_today`, not the system clock. Tools return only what is in the database.
- Board tables (`ticket_updates`, `drafts`, `purchase_orders`, `payment_requests`) are created on demand in the working copy. A reset removes them.

## Tools

### Read

| Tool | Reads | Purpose |
|---|---|---|
| `get_shop_today()` | `desk` | The shop's "today" for every date check. |
| `list_tickets()` | `tickets` | Every ticket with `is_resolved` (used by the backend's ticket route). |
| `list_open_tickets()` | `tickets` | Every ticket not resolved or declined. |
| `get_ticket(ticket_id)` | `tickets`, `ticket_updates`, `drafts`, `purchase_orders`, `payment_requests` | One ticket plus everything already on the board for it. |
| `check_stock(sku, size, qty_needed=0)` | `inventory` | Exact on-hand count and shortfall. Internal only. |
| `check_availability(sku, size, qty_needed=1)` | `inventory` | Customer-safe: `in_stock` / `not_enough_in_stock` / `out_of_stock`, with no count. |
| `check_pricing(sku, qty=1, discount_pct=0)` | `pricing` | Unit cost, list price, margins at list and at a discount, break-even discount. |
| `check_vendor_status(vendor_id=None)` | `vendors`, `invoices`, `desk` | Specialty, lead days, open invoices (with days overdue), and whether the vendor will ship. |
| `check_rent_due(lease_id)` | `leases`, `cash_accounts`, `desk` | Rent, next due date, days until due, and whether cash covers it. |
| `check_cash()` | `cash_accounts`, `payment_requests`, `payments` | Balance, pending total, balance if all pending were approved, and payments made. |
| `list_pending_approvals()` | `payment_requests` | Everything waiting for a human decision. |

### Write (board and requests)

| Tool | Writes | Rules enforced |
|---|---|---|
| `update_ticket(ticket_id, agent, note, status=None)` | `ticket_updates`, `tickets.status` | Valid statuses only. The original ticket notes are never overwritten. |
| `save_draft(ticket_id, audience, recipient, subject, body, author)` | `drafts` | Never sent. Customer drafts must use the requester's name and may not reveal shop finances, internal dollar figures or stock counts. |
| `create_purchase_order(vendor_id, sku, size, qty, requested_by, ticket_id=None)` | `purchase_orders`, `payment_requests` | Refused if the vendor has an open invoice. Cost comes from `pricing`, arrival is `date_today + lead_days`, and the payment is queued for approval. |
| `request_payment(kind, ref_id, requested_by, reason, ticket_id=None)` | `payment_requests` | `kind` is `invoice`, `rent` or `purchase_order`. The amount is looked up from the DB, and duplicates are refused. Nothing is paid. |

### Human only (hidden from every agent; called by `POST /api/approvals/{id}/approve` and `/reject`)

| Tool | Writes | Rules enforced |
|---|---|---|
| `approve_payment(request_id, approved_by, note="")` | `payments`, `cash_accounts`, `payment_requests`, plus `invoices.status` / `leases.next_due` / `purchase_orders.status`, `tickets.status`, `ticket_updates` | `approved_by` must be a human, not an agent name. Refuses if the balance would go negative. If it was the ticket's last pending payment, sets `tickets.status = 'resolved'` and logs a `human` row in `ticket_updates`. Everything is updated in one transaction. |
| `resolve_ticket_after_run(ticket_id, note="")` | `tickets.status`, `ticket_updates` | **System only**: called by the runner when a run ends. Resolves the ticket unless a payment for it is pending. |
| `reject_payment(request_id, rejected_by, note="")` | `payment_requests` (and `purchase_orders.status`) | No money moves. |

## Reset

```bash
.venv/bin/python mcp_server/reset_db.py
```

Copies the original over the working copy and checks they are identical. This is a script, not an MCP tool, so no agent can call it.

## Connect and smoke-test

`.mcp.json` at the project root registers this server (`campus-customs`, stdio) for the vibe coder and for the backend agent team. To call the first three tools over MCP and check the answers against the database:

```bash
.venv/bin/python mcp_server/smoke_test.py
```

Evidence is written to `output/mcp_smoke.json`.
