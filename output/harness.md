# Harness: Campus Customs Multi-Agent Operations

This file is the map of the whole system: the data and how the tables connect, the 18 MCP tools, the five agents, the API routes, the dashboard, the safety rules, and the results of the full run.

**Contents:** Databases · Tables · Open tickets · First three MCP tools · Agent team · All MCP tools · Backend routes · Dashboard · Safety guardrails · Shop rules · Full run results

## Databases

| File | Role |
|---|---|
| `data/campus_customs.db` | Original snapshot. Never written to. It is the source for every reset. |
| `data/campus_customs_new.db` | Working copy. The MCP server and backend read from and write to this file only. |

---

## Tables

### `desk`
**Fields:** `date_today` (TEXT), `notes` (TEXT)

**Why it matters:** `date_today` (2026-08-31) is "today" for the shop. Every overdue or due-soon check uses it, never the system clock.

### `tickets`
**Fields:** `id` (PK), `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` (FK → leases), `invoice_id` (FK → invoices), `status`, `notes`, `created_at`

**Why it matters:** These are the work queue. The Boss routes each ticket by `type`, and the optional `sku`/`size`/`lease_id`/`invoice_id` fields point each agent to the rows it needs.

### `inventory`
**Fields:** `sku`, `name`, `size`, `qty`, `location` (PK = `sku` + `size`)

**Why it matters:** Inventory checks stock by SKU **and** size to find shortfalls (ticket `qty` − on-hand `qty`).

### `pricing`
**Fields:** `sku` (PK), `unit_cost`, `list_price`

**Why it matters:** Accounting uses it to compute margins, to decide how far a discount can go, and to cost restock purchase orders.

### `vendors`
**Fields:** `id` (PK), `name`, `specialty`, `lead_days`

**Why it matters:** Inventory matches a SKU to a vendor by `specialty` and uses `lead_days` to estimate when restocked items will arrive.

### `leases`
**Fields:** `id` (PK), `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

**Why it matters:** Facilities uses `next_due` and `monthly_rent` to schedule rent. After rent is paid, `next_due` moves forward one month.

### `cash_accounts`
**Fields:** `name` (PK), `balance`, `date`

**Why it matters:** This is the only cash the shop has (checking = $3,400). The pay tool refuses any payment that would push `balance` below 0. Money only goes out.

### `payments`
**Fields:** `id` (PK), `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

**Why it matters:** This is the audit trail of money out. A row is written only after a human approves, and `approved_by` records who approved it. It starts empty.

### `invoices`
**Fields:** `id` (PK), `vendor_id` (FK → vendors), `amount`, `due_date`, `status`, `description`

**Why it matters:** An `open` invoice blocks that vendor from shipping. An invoice is overdue when `due_date` < `desk.date_today`. When it is paid, `status` changes to `paid`.

### Board tables (added by the MCP server; working copy only, removed by a reset)

| Table | Fields | Why it matters |
|---|---|---|
| `ticket_updates` | `id`, `ticket_id`, `agent` (agent, `human` or `system`), `status`, `note`, `created_at` | The ticket's history: the Boss's call, and who resolved it and how. The customer's original `tickets.notes` is never overwritten. |
| `drafts` | `id`, `ticket_id`, `audience`, `recipient`, `subject`, `body`, `author`, `status`, `created_at` | Every message the agents wrote. `status` is always `draft`; nothing is sent. |
| `purchase_orders` | `id`, `vendor_id`, `sku`, `size`, `qty`, `unit_cost`, `total_cost`, `expected_arrival`, `ticket_id`, `requested_by`, `status`, `created_at` | Restock orders, costed from `pricing` and dated with `lead_days`. They only become `ordered` after a human pays them. |
| `payment_requests` | `id`, `kind`, `ref_id`, `payee`, `amount`, `account`, `ticket_id`, `requested_by`, `reason`, `status`, `created_at`, `decided_by`, `decided_at`, `decision_note`, `payment_id` | The approval queue: what an agent prepared, and which human approved or rejected it. A paid request links to its `payments` row. |

---

## Open tickets and how they link

| Ticket | Type | Links to | What the data says |
|---|---|---|---|
| **101**: Tauhid Zaman, Bulldog tee S × 1 | `customer_order` | inventory (CC-TEE-WHITE, S), pricing, invoice **501** → vendor **1** Bulldog Print Co | 0 in stock, so the shortfall is 1. Invoice 501 ($840, "Rush reprint CC-TEE-WHITE S") was due 2026-08-28 and is **3 days overdue**. It blocks Bulldog Print Co from shipping. Lead time is 5 days. |
| **102**: Elm City Properties, rent due | `rent_notice` | lease **1** (Chapel Street shop), cash_accounts | Rent is $2,400, due 2026-09-02 (in 2 days, not yet overdue). |
| **103**: Yale AI Club, bulk hoodie discount, M × 20 | `price_override` | inventory (CC-HOOD-NAVY, M), pricing, vendors (apparel → Bulldog Print Co) | 8 in stock, so the shortfall is 12. Cost is $22 and list price is $58 ($36 margin, 62%). The restock vendor is the same one blocked by invoice 501. |

### Cross-ticket constraints
- **Cash:** $3,400 covers invoice 501 ($840) and rent ($2,400), which total $3,240 and leave **$160**. A 12-hoodie restock costs about $264 (12 × $22), which that $160 cannot cover.
- **Vendor block:** Tickets 101 and 103 both need Bulldog Print Co, which will not ship until invoice 501 is paid. If it is paid today, restocked items arrive around **2026-09-05** (5 lead days).

---

## First three MCP tools (Problem 3)

These three tools are read-only and point at `data/campus_customs_new.db`.

| Tool | Reads | Unlocks ticket | Why it is the right tool |
|---|---|---|---|
| `check_stock(sku, size, qty_needed)` | `inventory` | **101** (tee S × 1), **103** (hoodie M × 20) | Both tickets depend on whether the exact SKU and size is on the shelf. This tool returns the on-hand count and shortfall (101 is short 1, 103 is short 12), so the agents know a restock is needed. |
| `check_vendor_status(vendor_id)` | `vendors`, `invoices`, `desk` | **101** (invoice 501), and the restock for **103** | Ticket 101 links to invoice 501, which is open and 3 days overdue. That invoice blocks Bulldog Print Co from shipping the tee or hoodies. This tool shows the block and the 5-day lead time in one call. |
| `check_rent_due(lease_id)` | `leases`, `cash_accounts`, `desk` | **102** (rent notice) | Ticket 102 links to lease 1. This tool confirms the $2,400 rent is due in 2 days, checks it against `desk.date_today`, and shows whether checking ($3,400) can cover it before Accounting prepares a payment. |

---

## Agent team (Problem 5, `backend/`)

Built with PydanticAI. Every agent uses **`gpt-6-luna` through Portkey** (`backend/config.py` is the only place a model is named, and the loop stops if a response reports any other model). Portkey reports responses as `gpt-6-luna-global`, which the check accepts as `gpt-6-luna`. Every agent has a `delegate(to, task)` tool and can hand work to **any** other agent (full connectivity), within a per-ticket budget of 12 delegations and a chain at most 3 deep.

| Agent | File / prompt | Job | MCP tools it can call |
|---|---|---|---|
| **Boss** | `agents/boss.py` / `prompts/boss.md` | Reads each ticket, routes work, verifies reports, makes the final call, sets ticket status | `get_shop_today`, `list_open_tickets`, `get_ticket`, `update_ticket`, `list_pending_approvals`, `check_stock`, `check_availability`, `check_pricing`, `check_vendor_status`, `check_rent_due`, `check_cash` |
| **Inventory** | `agents/inventory.py` / `prompts/inventory.md` | Stock by SKU **and** size, shortfalls, which vendor restocks and whether they will ship | `get_shop_today`, `get_ticket`, `check_stock`, `check_availability`, `check_vendor_status` |
| **Accounting** | `agents/accounting.py` / `prompts/accounting.md` | Cash, invoices, margins. Queues payments and purchase orders for human approval | `get_shop_today`, `get_ticket`, `check_cash`, `list_pending_approvals`, `check_vendor_status`, `check_rent_due`, `check_pricing`, `check_stock`, `request_payment`, `create_purchase_order` |
| **Facilities** | `agents/facilities.py` / `prompts/facilities.md` | Lease, rent, landlord replies | `get_shop_today`, `get_ticket`, `check_rent_due`, `list_pending_approvals`, `save_draft` |
| **Customer Service** | `agents/customer_service.py` / `prompts/customer_service.md` | Drafts customer replies. Never sees costs, cash or exact counts | `get_shop_today`, `get_ticket`, `check_availability`, `save_draft` |

**Agent loop** (`backend/team.py`): the Boss runs once per ticket with `Agent.iter()`. Each node is appended to `output/audit_trail.json` as it happens: `run_start`, `user_prompt`, `model_request` (tool returns), `model_response` (tool calls, text, model name, token usage), and `run_end` (structured output) or `error`. Delegations appear as nested runs with the same `run_id`, plus `parent_agent` and `depth`. The file is append-only: it is file-locked, read, appended to and atomically replaced, and never wiped.

Outputs (`backend/models.py`): specialists return a `SpecialistReport`, and the Boss returns a `BossDecision`. Both carry a `facts` list (tool, field, value), so every claim traces back to an MCP tool call.

Run: `.venv/bin/python -m backend.run_tickets`. A full run resets the database first.

---

## MCP tools (all 18, `mcp_server/server.py`)

All tools run against `data/campus_customs_new.db`. The board tables (`ticket_updates`, `drafts`, `purchase_orders`, `payment_requests`) are created on demand in the working copy only. A reset removes them.

| Tool | Kind | Tables used | Unlocks |
|---|---|---|---|
| `get_shop_today()` | read | `desk` | All: "today" for every date check |
| `list_tickets()` | read | `tickets` | Backend: every ticket with open/resolved, for the dashboard |
| `list_open_tickets()` | read | `tickets` | All: the work queue |
| `get_ticket(ticket_id)` | read | `tickets`, `ticket_updates`, `drafts`, `purchase_orders`, `payment_requests` | All: the ticket plus its board history, so nothing is duplicated |
| `check_stock(sku, size, qty_needed)` | read (internal) | `inventory` | 101, 103: exact count and shortfall |
| `check_availability(sku, size, qty_needed)` | read (customer-safe) | `inventory` | 101, 103: in stock / not enough / out of stock, with no count |
| `check_pricing(sku, qty, discount_pct)` | read (internal) | `pricing` | 103: margin at list and at a discount, break-even |
| `check_vendor_status(vendor_id)` | read | `vendors`, `invoices`, `desk` | 101, 103: lead days, open invoices, will it ship |
| `check_rent_due(lease_id)` | read | `leases`, `cash_accounts`, `desk` | 102: rent, due date, can checking cover it |
| `check_cash()` | read | `cash_accounts`, `payment_requests`, `payments` | All money decisions: balance, pending total, what's left |
| `list_pending_approvals()` | read | `payment_requests` | All money decisions: what's waiting for a human |
| `update_ticket(ticket_id, agent, note, status)` | write | `ticket_updates`, `tickets.status` | All: records the Boss's decision |
| `save_draft(ticket_id, audience, recipient, subject, body, author)` | write | `drafts` (checks against `tickets`, `pricing`, `leases`, `invoices`, `cash_accounts`, `payments`, `payment_requests`, `purchase_orders`) | 101, 103 customer replies; 102 landlord reply. Never sent |
| `create_purchase_order(vendor_id, sku, size, qty, requested_by, ticket_id)` | write (request) | `purchase_orders`, `payment_requests` (reads `vendors`, `invoices`, `inventory`, `pricing`, `desk`) | 101, 103 restock. Refused while the vendor has an open invoice |
| `request_payment(kind, ref_id, requested_by, reason, ticket_id)` | write (request) | `payment_requests` (reads `invoices`, `leases`, `purchase_orders`, `vendors`, `cash_accounts`) | 101 (invoice 501), 102 (rent). Amount is pulled from the DB |
| `approve_payment(request_id, approved_by, note)` | **human only** | `payment_requests`, `payments`, `cash_accounts`, `invoices` / `leases` / `purchase_orders`, `tickets`, `ticket_updates` | Pays after human approval. Refuses if cash would go negative. Resolves the ticket when its last pending payment is paid |
| `resolve_ticket_after_run(ticket_id, note)` | **system only** | `tickets.status`, `ticket_updates` (reads `payment_requests`) | Run finished: resolve the ticket unless a payment waits on a human |
| `reject_payment(request_id, rejected_by, note)` | **human only** | `payment_requests`, `purchase_orders` | Human declines. No money moves |

`mcp_server/reset_db.py` (not an MCP tool, so no agent can call it) copies `campus_customs.db` over the working copy and confirms they are byte-identical.

---

## Backend routes (Problem 7, `backend/main.py`)

Start from `backend/`: `uvicorn main:app --reload --port 8000` (with the project venv active, or `../.venv/bin/python -m uvicorn main:app --reload --port 8000`). Every route reads and writes through the campus-customs MCP server.

- `GET /api/tickets`: all three tickets with `status` and `state` (open/resolved). A **resolved** ticket also carries `efficiency`, the score of its latest run against its Problem 6 plan.
- `GET /api/tickets/{id}`: one ticket with its board history (updates, drafts, purchase orders, payment requests).
- `GET /api/tickets/{id}/summary`: short summary of the latest run: the Boss's call, each specialist's report, and the drafts, payment requests and POs on the board.
- `GET /api/tickets/{id}/efficiency`: the efficiency score of a ticket's latest run, open or resolved, plus **improvement tips**, each with the points it would win back.
- `POST /api/tickets/{id}/run`: starts the agent team on that ticket in the background (202). Only one run at a time, and never on a closed ticket (409 otherwise). When the run finishes, the ticket is **resolved** unless a payment for it is waiting on a human.
- `GET /api/runs`: state of each ticket's latest run (running, done or error) and the Boss's decision.
- `GET /api/events?limit=&since=&ticket_id=&run_id=&include_history=`: recent agent events from the audit trail: who acted, what they said, which tools they called and what came back. Poll with `since=next_since`. Only events since the last reset are returned unless `include_history=true`; the file itself is never trimmed.
- `GET /api/approvals`: payment and purchase-order requests waiting for a human.
- `POST /api/approvals/{request_id}/approve`: **human-only cash movement.** Body `{"approved_by": "<name>", "note": ""}`. Pays the request, updates `payments`, `cash_accounts` and the invoice, lease or PO, and logs a `human_decision` event. If it was the ticket's last pending payment, the ticket becomes `resolved` (logged in `ticket_updates` as `human`), so its efficiency score shows. Returns 409 if cash would go negative.
- `POST /api/approvals/{request_id}/reject`: human declines a request. No money moves.
- `GET /api/cash`: current checking balance from `cash_accounts`, plus the pending total and the balance if everything pending were approved.
- `POST /api/reset`: copies `campus_customs.db` over the working copy for a fresh run (refused while a run is in progress). The audit trail is kept.
- `GET /api/health`: liveness, the model name, the active run and the shop date (`desk.date_today`).

The dashboard (`frontend/`, Problem 8) calls these from http://localhost:5173, which the backend's CORS allow-list permits.

**Efficiency, one source of truth:** the ticket plans, penalty weights and rating thresholds live in a JSON block inside `output/desk_tickets.html` (`id="ticket-plans"`). The page's meter and `backend/efficiency.py` both read it.

---

## Dashboard (Problem 8, `frontend/`)

React + Vite + TypeScript. Start with `npm run dev` (http://localhost:5173). It calls the routes above at http://localhost:8000. The look and the reasons behind it are in `output/design.md`.

| Part | What it shows or does | Routes it uses |
|---|---|---|
| Header | Campus Customs pennant logo, **checking balance** (pending and after), "to approve" count, **Reset shop** (asks first; disabled during a run) | `/api/cash`, `/api/approvals`, `/api/health`, `POST /api/reset` |
| Hero | The Yale fans photo from the store, with Open, Needs you and Resolved counters | `/api/tickets` |
| The board | All three tickets with status and an ⚡ efficiency badge once resolved | `/api/tickets` |
| Run agent team | Starts the team on the selected ticket. Disabled while another ticket runs or a payment is pending | `POST /api/tickets/{id}/run`, `/api/runs` |
| Agent roster | Each agent: not called, working, or reported back | `/api/events` |
| Agent activity | Live feed (every 1.2 s): who said what, tool calls in plain English plus MCP names, delegations indented, results folded | `/api/events` |
| Approval card (gold) | What was prepared, the amount, the payee, the reason, and **checking after**. Needs your name; Approve or Reject | `POST /api/approvals/{id}/approve` / `reject` |
| What the team did | The Boss's call, one line per specialist, and drafts, payments and POs on the board | `/api/tickets/{id}/summary` |
| Efficiency | Score gauge, budget meters, and "how to do better next time" tips | `/api/tickets/{id}/efficiency` |

---

## Safety guardrails

What a real business would want before agents touch real customers and real money, and how this build handles each one. Nothing here contacts a real customer, landlord or vendor.

| Guardrail | How it is enforced |
|---|---|
| **No invented information.** Use only real data from the records, with no inferences beyond plain arithmetic on tool values. | Prompts require every number to appear in `facts` with its source tool and field. Payment and PO amounts are looked up in the DB by the tool, never typed by an agent. Unknown IDs return "not found" rather than a guess. |
| **Address customers by name.** | `save_draft` refuses a customer draft whose recipient isn't the ticket's requester or whose body doesn't use their name. |
| **Stock: say in stock or out of stock, never how many.** | Customer Service only has `check_availability`, which returns no count. `save_draft` also refuses phrases like "only 2 left" or "8 available". |
| **No shop financials to customers** (rent, bills, invoices, debt, cash, costs, margins, vendors). | Customer Service has no financial tools. `save_draft` refuses customer drafts containing financial terms or any internal dollar figure (unit cost, rent, invoice, balance, payment, PO total). A customer's approved price is allowed. |
| **Today is `desk.date_today`.** | Every date check in the tools reads `desk`. The system clock is never used for business dates. |
| **Lead times come from `vendors.lead_days`.** | `create_purchase_order` computes arrival as `date_today + lead_days`. |
| **No shipping while a vendor has an open unpaid invoice.** | `create_purchase_order` refuses, and `approve_payment` re-checks before paying a PO. |
| **Human approval for every payment.** | Agents can only `request_payment` / `create_purchase_order`. `approve_payment` and `reject_payment` are filtered out of every agent's toolset and refuse an agent name as approver. The only caller is `POST /api/approvals/{id}/approve`, which needs a human name and logs a `human_decision` audit event. |
| **Update the relevant table when paid.** | `approve_payment` runs one transaction: insert into `payments` (with `approved_by`), lower `cash_accounts.balance`, then mark the invoice `paid`, move `leases.next_due` forward a month, or mark the PO `ordered`. |
| **No negative balances.** | `approve_payment` refuses if the balance would drop below 0. `check_cash` and the request tools show what would be left if everything pending were approved. |
| **Cash only goes out.** | No tool adds money. There is no revenue or deposit tool. |
| **Reset before a full run.** | `run_tickets` resets the working DB before any full run and logs a `db_reset` event. `--no-reset` is only allowed for single tickets. |
| **No real emails or vendor calls.** | There is no send tool. `save_draft` stores `status='draft'` and returns `sent: false`. |
| **Only `gpt-6-luna`.** | One constant in `backend/config.py`. The loop stops and logs an error if a response reports another model. |
| **Auditability.** | Every agent-loop step is appended to `output/audit_trail.json` with run id, ticket, agent, parent, depth, step, model and token usage. |
| **No runaway loops or spend.** | 12 delegations and a chain at most 3 deep per ticket, no self-delegation, and a model-request cap per ticket. |
| **Approvals record a real person.** | The board won't send an approval without a name in "Approving as". The backend refuses an empty name or an agent's name. When the human approved in chat and the assistant sent the call, the request's `decision_note` says so. |
| **Tickets resolve only when nothing waits on a human.** | When a run finishes, `resolve_ticket_after_run` closes the ticket only if no payment is pending. Otherwise it closes when the human approves the last pending payment. |
| **One run at a time; no re-running closed tickets.** | Tickets share one checking account, so `POST /run` refuses while another run is active or the ticket is already resolved. Reset is also refused mid-run. |
| **Agents can't reset, approve or close tickets.** | `reset_db.py` isn't an MCP tool. `approve_payment`, `reject_payment` and `resolve_ticket_after_run` are hidden from every agent's toolset (`HUMAN_ONLY_TOOLS`). |
| **The board shows the current shop only.** | After a reset, the board shows only runs since that reset, so old results never look current. The audit file itself is never trimmed. |
| **Secrets stay secret.** | `PORTKEY_API_KEY` is loaded from `.env` (git-ignored). `.env.example` holds the variable name only. |

---

## Shop rules (enforced in tools, not just prompts)
1. "Today" = `desk.date_today`.
2. Lead times come from `vendors.lead_days`.
3. No restock or purchase order to a vendor with an `open` invoice.
4. Every payment needs human approval. On payment: insert into `payments`, reduce `cash_accounts.balance`, and update the target (`invoices.status = 'paid'`, advance `leases.next_due`, or `purchase_orders.status = 'ordered'`).
5. The pay tool refuses if cash would go negative.
6. Cash only goes out. No revenue.
7. Reset `campus_customs_new.db` from the original before every full run.
8. No real emails or vendor calls. Drafts stay on the board.
9. Model: `gpt-6-luna` via Portkey only.

---

## Full run results (Problem 9)

Reset from the board at 2026-10-27 10:55. All three tickets were run from the board, then the human approved the two payments (overdue invoice first). The details are in `output/desk_tickets.html` (Actual sections and Cash tab), `output/resolved_tickets.json` and `output/resolved_board.html`, built by `scripts/build_problem9_report.py` from the audit trail and the database.

| Ticket | Agents (beyond the Boss) | Delegations | Efficiency | Resolved by | Cash |
|---|---|---|---|---|---|
| 101 Bulldog tee | Inventory, Accounting, Customer Service | 3 (plan 3) | 80 Acceptable | Human approval of request #1 | −$840.00 (invoice 501) |
| 102 Rent due | Facilities, Accounting (called twice) | 3 (plan 2) | 62 Acceptable | Human approval of request #2 | −$2,400.00 (lease 1 rent) |
| 103 Bulk hoodies | Inventory, Accounting, Customer Service | 3 (plan 3) | 85 Efficient | Run finished; nothing waiting | $0.00 (vendor blocked, no PO) |

**Cash:** starting $3,400.00 − $840.00 − $2,400.00 − $0.00 = **$160.00**, which equals `cash_accounts.balance` (checking) in `data/campus_customs_new.db`. The balance never went negative.
