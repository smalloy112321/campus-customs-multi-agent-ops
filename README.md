# Campus Customs: Multi-Agent Operations

AI for Managers, Homework 5. A team of five AI agents runs the Campus Customs shop desk: customer orders, rent, unpaid bills and discount requests. A human watches them work on a React board and approves every payment.

| Piece | Folder | What it does |
|---|---|---|
| **MCP server** | `mcp_server/` | FastMCP tools over the shop database: reads, drafts, payment requests and purchase orders, plus human-only approval. Every shop rule is enforced here. |
| **Backend + agent team** | `backend/` | FastAPI routes plus five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service) with full delegation, all on **`gpt-6-luna` via Portkey**. |
| **Dashboard** | `frontend/` | React + Vite + TypeScript board: run a ticket, watch the agents live, approve payments, and see cash and efficiency. |

Data: `data/campus_customs.db` is the **original** (never written to) and `data/campus_customs_new.db` is the **working copy** that the MCP server and backend use. Both are committed. The working copy is checked in exactly as the Problem 9 full run left it (all three tickets resolved, checking $160.00). **Reset it before your own full run.**

---

## 1. Setup (once)

Requires Python 3.12+ (built on 3.14), Node 20+, and a Portkey API key.

```bash
git clone https://github.com/smalloy112321/campus-customs-multi-agent-ops.git
cd campus-customs-multi-agent-ops

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env              # then put your key in .env: PORTKEY_API_KEY=...
(cd frontend && npm install)
```

`.env` is git-ignored and is never committed. Every agent uses `gpt-6-luna` through Portkey; the model is fixed in `backend/config.py`.

## 2. Copy the original DB to the working copy (clean run)

Whenever you want a clean start, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
# or, the same copy plus a byte-for-byte check:
.venv/bin/python mcp_server/reset_db.py
```

The original `data/campus_customs.db` is never written to. While the backend is running you can also reset with the board's **Reset shop** button or `curl -X POST localhost:8000/api/reset`.

## 3. Start the MCP server

The MCP server is a stdio server registered in `.mcp.json` as `campus-customs`. **The backend starts it automatically** (it reads `.mcp.json`), so for a normal run you can skip straight to step 4. To start or check it on its own:

```bash
.venv/bin/python mcp_server/server.py        # stdio server; waits for an MCP client (Ctrl+C to stop)
.venv/bin/python mcp_server/smoke_test.py    # connects through .mcp.json, calls tools, checks the answers against the DB
```

The smoke test rewrites `output/mcp_smoke.json` with whatever the working DB holds at that moment.

AI coding tools that read `.mcp.json` (for example Claude Code) can connect to the same server when opened in this folder.

## 4. Start the FastAPI backend (port 8000)

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
# (or with the venv activated: uvicorn main:app --reload --port 8000)
```

API docs are at http://localhost:8000/docs. CORS allows the board's origin (http://localhost:5173). Before restarting, check for an orphan server with `lsof -i :8000`, and stop the whole uvicorn process tree.

## 5. Start the React board (port 5173)

In a second terminal:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. Pick a ticket and click **Run agent team**. Watch each agent in the live feed. When a payment card appears, type your name in **Approving as** and click **Approve**; the checking balance drops and the ticket resolves.

## 6. Full three-ticket run (always reset first)

1. **Reset the DB**: click **Reset shop** on the board, or run step 2. Checking goes back to **$3,400.00**.
2. Run **101**, then **102**, then **103** from the board (one at a time; they share one checking account).
3. Approve the payment cards. The overdue invoice ($840, ticket 101) should go before rent ($2,400, ticket 102), as the agents advise. Ticket 103 resolves on its own with no money moved (its vendor is blocked).
4. Expected ending checking: **$3,400.00 − $840.00 − $2,400.00 = $160.00**.
5. Optional: rebuild the report pages from your run with `.venv/bin/python scripts/build_problem9_report.py`. It refuses to write anything if the cash ledger doesn't match `cash_accounts`.

Command-line alternative (no board): `.venv/bin/python -m backend.run_tickets` resets first, then runs all three. Payments still wait for a human approval through the API or board.

---

## Shop rules (enforced in the MCP tools, not just prompts)

- "Today" is `desk.date_today` (2026-08-31). Lead times come from `vendors.lead_days`.
- A vendor with an open, unpaid invoice will not ship: `create_purchase_order` refuses.
- **Every payment needs a human.** Agents can only *request* payments. `approve_payment` is hidden from every agent, refuses an agent name, and is only called by the board's Approve button. Paying updates `payments`, `cash_accounts`, and the invoice, lease or purchase order in one transaction.
- The pay tool refuses if cash would go negative. Cash only goes out.
- No real emails or vendor calls. Every message is a draft on the board.
- Customers are addressed by name and never see stock counts or shop finances (enforced by `save_draft`).

The full map is in `output/harness.md`.

## Deliverables (in `output/`)

| File | What it is |
|---|---|
| `harness.md` | Tables, all 18 MCP tools, the five agents, API routes, dashboard, safety guardrails, run results |
| `desk_tickets.html` | Double-click: per-ticket Expected plan vs Actual run, efficiency meter, **Cash** ledger, **Reflection** |
| `resolved_tickets.json` | Each ticket's final status, outcome, agent contributions and human approvals |
| `resolved_board.html` | Double-click: screenshots of the React board for each resolved ticket |
| `audit_trail.json` | Append-only log of every agent-loop step (never wiped) |
| `mcp_smoke.json` | MCP connection test: prompt, tool and output, checked against the DB |
| `design.md` | Dashboard look and the reasons behind it |
| `github_url.txt` | This repository's URL |
| `../AI_prompts.md` | Every prompt typed, one section per problem |

## File tree

Everything committed to this repository (`.venv/`, `node_modules/` and the real `.env` are git-ignored):

```text
campus-customs-multi-agent-ops/
├── backend/
│   ├── agents/   # one file per agent + delegate tool
│   │   ├── __init__.py
│   │   ├── accounting.py
│   │   ├── base.py
│   │   ├── boss.py
│   │   ├── customer_service.py
│   │   ├── facilities.py
│   │   └── inventory.py
│   ├── prompts/   # one prompt per agent
│   │   ├── accounting.md
│   │   ├── boss.md
│   │   ├── customer_service.md
│   │   ├── facilities.md
│   │   └── inventory.md
│   ├── __init__.py
│   ├── audit.py   # append-only audit trail writer
│   ├── config.py   # gpt-6-luna via Portkey (the only model)
│   ├── efficiency.py   # scores a run against the Problem 6 plan
│   ├── main.py   # FastAPI routes the board calls
│   ├── models.py   # Pydantic data types
│   ├── README.md
│   ├── requirements.txt   # Python dependencies
│   ├── run_tickets.py   # command-line runner (resets first)
│   └── team.py   # MCP connection + agent loop -> audit trail
├── data/
│   ├── campus_customs.db   # ORIGINAL shop database (never written to)
│   └── campus_customs_new.db   # WORKING copy used by the MCP server and backend
├── frontend/
│   ├── public/
│   │   └── favicon.svg
│   ├── src/
│   │   ├── assets/
│   │   │   └── hero-yale-fans.jpg
│   │   ├── components/
│   │   │   ├── ActivityFeed.tsx
│   │   │   ├── AgentRoster.tsx
│   │   │   ├── ApprovalCard.tsx
│   │   │   ├── EfficiencyPanel.tsx
│   │   │   ├── Header.tsx
│   │   │   ├── Hero.tsx
│   │   │   ├── Logo.tsx
│   │   │   ├── ScoreBadge.tsx
│   │   │   ├── SummaryPanel.tsx
│   │   │   ├── TicketList.tsx
│   │   │   └── TicketWorkspace.tsx
│   │   ├── agents.ts
│   │   ├── api.ts
│   │   ├── App.tsx
│   │   ├── index.css
│   │   ├── main.tsx
│   │   └── types.ts
│   ├── .env.example   # VITE_API_BASE (defaults to http://localhost:8000)
│   ├── .gitignore
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── README.md
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── mcp_server/
│   ├── __init__.py
│   ├── README.md
│   ├── requirements.txt   # Python dependencies
│   ├── reset_db.py   # copy original -> working copy, with a byte check
│   ├── server.py   # 18 MCP tools; every shop rule enforced here
│   └── smoke_test.py   # calls tools over MCP and checks them against the DB
├── output/
│   ├── screenshots/
│   │   ├── ticket-101.png
│   │   ├── ticket-102.png
│   │   └── ticket-103.png
│   ├── audit_trail.json   # append-only log of every agent step
│   ├── design.md
│   ├── desk_tickets.html   # Expected vs Actual, Cash ledger, Reflection
│   ├── github_url.txt   # this repository's URL
│   ├── harness.md   # tables, tools, agents, routes, dashboard, safety
│   ├── mcp_smoke.json
│   ├── resolved_board.html   # screenshots of the board, per resolved ticket
│   └── resolved_tickets.json
├── scripts/
│   └── build_problem9_report.py   # builds Actual/Cash, resolved_tickets.json, resolved_board.html
├── .env.example   # copy to .env and add PORTKEY_API_KEY (real .env is never committed)
├── .gitignore
├── .mcp.json   # registers the campus-customs MCP server (stdio)
├── AI_prompts.md   # every prompt typed, one section per problem
├── README.md
└── requirements.txt   # Python dependencies
```
