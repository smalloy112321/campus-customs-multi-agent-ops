# AI Prompts Log: Homework 5 (Campus Customs Multi-Agent Operations)

This is a log of the prompts I typed into the vibe coder. It has one section for each problem.

---

## Setup: Background and shop rules

**Prompt:**
> We are going to work on AI for Managers Homework 5. Before we get started, I am going to give you background on what we're doing. Then, I am going to give you step by step directions. Do not move to the next step before I tell you to.
>
> Background: Campus Customers Multi-Agent Operations is the agentic team that runs the shop (open tickets land on the board including customer orders, rent, unpaid bills, discount requests, and whatever else the shop has to handle). We will build three pieces that talk to each other: an MCP server, a FastAPI backend with a multi-agent team, and a React dashboard so that a human can watch the agents at work and approve requests. The agent team should have full connectivity - any agent can delegate tasks to any other agent for help. We'll build these agents:
> - The Boss: reads each ticket, decides who should work on it, makes final calls
> - Inventory: checks stock by SKU and size, spots shortfalls, and figures out which vendor can restock
> - Accounting: watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval
> - Facilities: handles the shop side (leases, rent, etc.)
> - Customer service: drafts messages for customers
>
> We will use the attached data (campus_customs.db). Tables include desk, tickets, inventory, pricing, vendors, leases, cash accounts, payments, and invoices. We will build tools to update the database as tickets get resolved. We will make a copy of the database file called data/campus_customs_new.db and point the MCP server and backend at that working copy. Keep campus_customs.db untouched so we can reset when we want to restart resolving the tickets.
>
> Rules of the shop:
> - The field desk.date_today is "today" for the shop. Use this date to determine what is overdue.
> - Vendor lead times come from the vendors table.
> - A vendor will not ship new product while they still have an open unpaid invoice.
> - Human approval is required for any payments. If payment is made, make sure to update the relevant table.
> - If there is not enough cash, the pay tool must refuse (no negative balances).
> - Cash only goes out in this homework (we did not model revenue, so no money comes in).
> - Before a full run to resolve the tickets, make sure to reset the database to the original values.
> - Do not email customers or call real vendors. Drafts stay on the board.
>
> Use my PORTKEY_API_KEY for AI calls. For this assignment, use only gpt-6-luna through Portkey for every agent. We will work one problem at a time. The final submission will be a public Github repo with the last problem showing the file tree.

**Follow-up:** None needed. The AI restated the architecture, data plan and shop rules, then waited for Problem 1.

---

## Problem 1: Create the AI prompts log

**Prompt:**
> Okay, let's get started. Problem 1. Create AI_prompts.md at the start of the assignment and keep it updated as you work. Put one section for each problem. Each section must include the following: the problem number and title, at least one prompt typed, and one follow-up prompt if needed.

**Follow-up:** None needed. The first prompt created this file with the required structure.

---

## Problem 2: Explore the database and start the harness

**Prompt:**
> Okay, Problem 2. First, open data/campus_customs.db and look through every table and fields. Copy the original file to data/campus_customs_new.db.
>
> Study the three open tickets and show them to me, telling me how they link to the other tables.
>
> Start output/harness.md. For each table, list the fields and one short line on why that matters for the agents. Show me the short line for each of the tables.

**Follow-up:** None needed. The AI copied the database, mapped each of tickets 101, 102 and 103 to its linked rows, and started `output/harness.md`.

---

## Problem 3: Build the MCP server (first three tools)

**Prompt:**
> Thank you. Ready for Problem 3. Write an MCP server in mcp_server/ using Fast MCP. It will talk to data/campus_customs_new.db. We are not connecting or running it yet. We will start with three tools needed for the tickets in the database. Keep names clear. Do not invent data, only use information in the database.
>
> In output/harness.md, list each of the three MCP tools. For each tool, let's include which table it reads, which ticket it helps unlock, and one sentence on why that tool is the right one for that ticket.
>
> We will also add a short mcp_server/README.md file that explains what the MCP server is for, which database file it uses, and the three tools it has.
>
> Please help me draft the three rules now with one sentence on why it's right. I will help rewrite with you.

**Follow-up prompt:**
> The three tool drafts look good. Keep them as written.

**Result:** No rewrite needed. I kept `check_stock`, `check_vendor_status` and `check_rent_due` as drafted.

---

## Problem 4: Connect the MCP server and smoke-test the tools

**Prompt:**
> Let's do Problem 4. Let's add the MCP server to this project so that the vibe coder can call the tools. Save the connection JSON text in .mcp.json at the project root. Once connected, test each of the three MCP tools we made in the last problem and save the evidence in output/mcp_smoke.json. For every tool, let's include the prompt that we asked the vibe coder, the tool name, and the tool output (which must match a value in data/campus_customs_new.db). Show me the tests when you are done.

**Follow-up:** None needed. The AI wrote `.mcp.json`, connected over stdio, called all three tools, and checked each output against the database. All three passed.

---

## Problem 5: Build the agent team and grow the MCP tools

**Prompt:**
> Ready for Problem 5. We are now going to build the agent team and grow the MCP tools. We will build the agentic team for Campus Customs using PydanticAI: boss, inventory, accounting, facility, and customer service (the agents I gave you when we talked about the background for this assignment). We will include prompts, models, and agent loops so that they can delegate work to each other with full connectivity.
>
> Put the agent prompts in backend/prompts/ with one file per agent. Put the data types in backend/models.py and the agent files under backend/
>
> Use my PORTKEY_API_KEY and only gpt-6-luna for every agent. Remember: points will be deducted if any other model shows up in the code or runs.
>
> I want each prompt to be one-of-a-kind (not directly from the assignment) with the shop rules that agent needs. I want to be as detailed as possible when writing the prompts (nothing short, nothing generic).
>
> Add any tools the agent needs to the MCP server so that they can work on the open tickets. Shop facts come from the MCP server over data/campus_customs_new.db. Do not invent a second shop-tools layer that bypasses MCP.
>
> Wire the agents so that they append to output/audit_trail.json as they run: for each agent-loop step and record enough to audit later. Append to this file. Do not wipe it clean each run.
>
> In output/harness.md, list each agent and each MCP tool including ones we add in this problem, along with which table the tool uses.
>
> Also, add a short safety section of the guardrails a real business would want when agents touch real customers and real money. Remember, we are not actually reaching out to any customers or businesses. Here are some safety rules:
> - Do not invent any information
> - Only recall real data, do not make inferences
> - Refer to customers by their name when they reach out
> - When speaking with customers, you can tell them if inventory is in stock or out of stock but do not tell them how much stock is available
> - Do not disclose any information related to financials to customers, including rent, bills, debt, etc.
> - The field desk.date_today is "today" for the shop. Use this date to determine what is overdue.
> - Vendor lead times come from the vendors table
> - A vendor will not ship new product while they still have an open unpaid invoice
> - Human approval is required for any payments.
> - If payment is made, make sure to update the relevant table
> - If there is not enough cash, the pay tool must refuse (no negative balances)
> - Cash only goes out in this homework (we did not model revenue, so no money comes in)
> - Before a full run to resolve the tickets, make sure to reset the database to the original values
> - Do not email customers or call real vendors. Drafts stay on the board.
>
> Update mcp_server/README.md so that the tool list matches what we have now.

**Follow-up prompt:**
> Do a live test run on ticket 101 only, so we can check the agents and the audit trail, then reset the database.

**Result:** The Boss delegated to Inventory, then Accounting, then Customer Service. Accounting queued a payment request for invoice 501 ($840), which is waiting for human approval; nothing was paid. Customer Service saved a draft to Tauhid saying the tee is out of stock, with no counts or finances. The Boss set ticket 101 to `waiting_approval`. The audit trail recorded 53 steps, all from gpt-6-luna, and the database was reset afterwards.

---

## Problem 6: Plan the three tickets (desk_tickets.html)

**Prompt:**
> Thanks. Let's do Problem 6. We are going to plan the three tickets. Before we wire the backend, I want to write down what we expect the team to do on each open ticket.
>
> Build output/desk_tickets.html, a page where I can double click with one tab per ticket (101, 102, and 103). Add empty "Cash" and "Reflection" tabs for later problems (leave blank for now).
>
> On each ticket tab, fill an "Expected" section only (leave room for an "Actual" section that we'll fill in later after we run the agents).
>
> For each ticket's Expected section, I want to write:
> - Who the boss should call first and why
> - All the agent delegations you expect (not "boss calls everyone")
> - Which MCP tools you'd expect that run to use
>
> Here are some general rules:
> - Each ticket should send as few specialists as possible
> - Plans that send every specialist on every ticket score low
> - It would be helpful to add a measurement tool to each call based on which specialist(s) are used and which tools are run to determine if the multi-agent operation is being efficient or needs to be made more efficient

**Follow-up:** None needed. The plans use 3, 2 and 3 specialists. Facilities is only on 102, and Inventory and Customer Service are skipped on 102. Each ticket tab has an efficiency meter that scores a run from `output/audit_trail.json`.

---

## Problem 7: Backend routes (FastAPI)

**Prompt:**
> Great. Let's do Problem 7 next, which are Backend Routes. The React frontend dashboard that we will do in the next problem needs a backend that it can call. In backend/main.py, use FastAPI and add routes that do the following:
> 1. Return the three tickets and whether each is opened or resolved
> 2. Take a ticket id and run your agent team on that ticket
> 3. Return recent agent events (what each agent said and which tools they used so that the board can refresh)
> 4. Approve a payment or purchase after a human clicks approve (agents only prepare the pay; this route is what actually changes cash)
> 5. Return the current checking balance from cash_accounts
> 6. Reset the database to the original values when you want to try a fresh run.
>
> From the backend/ folder, start the server with: uvicorn main:app --reload --port 8000
>
> In out/harness.md, list each route in one line (the URL and what it does)

**Follow-up prompt:**
> Upon second thought, let's also make sure that when a ticket is returned whethers its open or resolved, if its resolved it shows the efficiency number that we created in the last problem

**Result:** `GET /api/tickets` now includes an `efficiency` score for resolved tickets. It is computed by `backend/efficiency.py` from the same plan JSON the desk page uses, so both give the same score (101 = 96, 102 = 92). A live run of ticket 102 through `POST /api/tickets/102/run` went Boss → Facilities → Accounting and queued payment request 1 ($2,400 rent) for approval. The AI did not approve the payment itself; that is left for me.

**Follow-up prompt 2:**
> Leave it pending. I'll approve request 1 myself with the curl command, then you check the cash and lease.

**Result:** I approved request 1 with curl. The AI confirmed checking went from $3,400 to $1,000, payment #1 was recorded with my name, lease 1's next due date moved to 2026-10-02, and a `human_decision` event was logged.

**Follow-up prompt 3:**
> Yes: when a human approves the last pending payment on a ticket, mark that ticket resolved (logged as a human update) so its efficiency score shows.

**Result:** `approve_payment` now resolves the ticket in the same transaction when no other payment on that ticket is pending, and logs a `human` row in `ticket_updates`. Tested on a scratch DB: first of two payments leaves it open, the last resolves it, and refused or ticketless payments change nothing.

**Follow-up prompt 4:**
> Reset the database and rerun ticket 102 through the API; I'll approve the rent again myself so it resolves under the new rule.

**Follow-up prompt 5** (after my curl and /docs attempts didn't reach the server):
> I approve payment request 1 ($2,400 rent to Elm City Properties, ticket 102). Send the approve call for me with approved_by "Samantha Malloy", then recheck ticket 102.

**Result:** The rerun went Boss → Facilities → Accounting. After my approval, cash went from $3,400 to $1,000, lease 1's next due date moved to 2026-10-02, and ticket 102 became `resolved`, logged as a human update. `GET /api/tickets` now shows 102 as resolved with efficiency 92 (Efficient).

---

## Problem 8: React dashboard (frontend/)

**Prompt:**
> Great. Let's do Problem 8 now. Next we are going to build a frontend dashboard in frontend/ with React + Vite + TypeScript. The page should call the routes that we built in Problem 7. At minimum, the board should:
> * List all three tickets
> * Let you pick one ticket and start the agent team on it
> * Show each agent and what they are saying and doing while the ticket runs
> * Mark a ticket resolved when the run finishes
> * Show a short summary of what agent did on that ticket
> * Show the efficiency score and how it could better be improved for knowledge for next time
> * Let a human approve a pay or purchase when asked
> * Show the checking balance (it should drop after an approved pay)
>
> I also want the dashboard to look good. Let's borrow inspiration from when I built the last Campus Customs website - especially the picture we used on the homescreen and the logo we created. Once you make it, I'll give you more feedback to make it look as sleek and polished as possible.
>
> The front end should talk to the backend at http://localhost:8000. On the backend, allow the Vite page origin (usually http://localhost:5173) so the browser is allowed to call those routes. Start the board with npm run dev.
>
> Write output/design.md with what we've chosen for the dashboard look, including the changes we're about to make - we should include what changes we made, why we made the changes to make the site as user friendly and enjoyable as possible

**Follow-up prompts (approval check):**
> I approved the $840 on ticket 101 from the board. Check that the balance dropped and 101 resolved, then I'll give design feedback.

> I approve payment request 1 ($840 to Bulldog Print Co, invoice 501, ticket 101). Send the approve call for me with approved_by "Samantha Malloy", then check the balance and that 101 resolved.

**Result:** My clicks on the board never reached the backend. First the servers had been stopped while idle; then the "Approving as" name was empty. I approved in chat and the AI sent the call. Checking went from $3,400 to $2,560, invoice 501 is `paid`, and ticket 101 resolved with efficiency 96. The board updated on its own: balance $2,560, Needs you 0, Resolved 2. Design follow-up: the Approve button shouldn't fail silently when the name is missing.

**Follow-up:** _(design feedback round to come)_

**Result so far:** The board reuses the Homework 4 pennant logo, the Yale fans hero photo, the Yale blue and cream palette, and the store's fonts. Run from the dashboard: ticket 101 went Boss → Inventory, Accounting, Customer Service and stopped at a gold approval card for $840. Ticket 103 went Boss → Inventory, Accounting, Customer Service and was marked resolved when the run finished, with efficiency 92. The backend gained a summary route, improvement tips, and resolve-on-run-finish.

---

## Problem 9: Full run over all three tickets

**Prompt:**
> Great. Let's do Problem 9. Before testing the agents on a full run over the three tickets, I want to reset the working database data/campus_customs_new.db to start clean. First, let's note what the starting check balance is. Then, let's run all three tickets on the board (101, 102, and 103) until each is resolved.
>
> Open output/desk_tickets.html from Problem 6. On each ticket tab, fill the Actual section in from this run, including which agents worked, what they delegated, which tools they used, and their efficiency. Keep the expected section so that we can compare the two.
>
> On the cash tab of the same output/desk_tickets.html, itemize the money:
> - starting checking balance (after the reset)
> - for each ticket, how cash changed when that ticket resolved and which (which pay / purchase, dollar amount)
> - ending checking balance, it must match cash_accounts in the working database
>
> Wrong cash math loses points even if the board shows every ticket resolved
>
> Save output/resolved_tickets.json for each ticket (id, final status, short outcome, what each agent contributed, any human approvals)
>
> Save output/resolved_board.html (a page I can double-click with a screenshot of the React board for each resolved ticket 101, 102, and 103)
>
> Append real runs to output/audit_trail.json. Finish output/harness.md so that it covers tables, MCP tools, the five agents, API routes, the dashboard, and all of the safety rules.

**Follow-up prompt:**
> I approve payment request 1 ($840 to Bulldog Print Co, invoice 501, ticket 101) and payment request 2 ($2,400 rent to Elm City Properties, lease 1, ticket 102). Send both approve calls for me with approved_by "Samantha Malloy", request 1 first, then finish Problem 9.

**Result:** Reset from the board (starting checking $3,400.00). All three tickets were run from the board. 103 resolved when its run finished ($0, vendor blocked). 101 and 102 resolved after my approvals: −$840.00 and −$2,400.00. Ending checking is $160.00, which matches `cash_accounts`. Efficiency was 80, 62 and 85. On 102, Accounting was called twice (once by Facilities, once by the Boss), so it lost points. `scripts/build_problem9_report.py` builds the Actual and Cash sections, `resolved_tickets.json` and `resolved_board.html` straight from the audit trail and the database, and stops if the cash doesn't reconcile.

---

## Problem 10: Reflection

**Prompt:**
> Ok let's do Problem 10. Open output/desk_tickets.html and fill the Reflection tab.
>
> Please help me write a reflection based on our back-and-forth during this problem set. I want it to include:
> - For each ticket, how did the Actual compare to the Expected plan that we wrote?
> - What would have been simpler as one agent with tools and why?
> - Describe three new problems Campus Customs might face that this agent team can solve with the tools we built
> - Describe three new problems Campus Customs might face that this agent team could not solve with the tools we built and explain what new tools or agents we would need to solve them
>
> Every answer should tie to this app and the three tickets we ran using the ticket tabs and cash tab as evidence. Generic AI essays without Campus Customs details will score low.

**Follow-up:** None needed. The reflection cites run evidence from the ticket and Cash tabs:
- 101 matched the plan, but the Boss repeated its own calls.
- 102 had an extra Accounting handoff, which also produced the "pay the invoice first" advice.
- 103's Boss declined to quote any price.
- One-agent evidence: `get_shop_today` was called 12 times, and 102 used 22 calls where 5 would do.

It names three solvable problems (the $8 tee restock, Crest Mugs from Elm City Gifts, a 30-cap order) and three unsolvable ones (rent of $2,400 due 2026-10-02 against $160 with no money coming in, receiving restocks while the shop date is frozen, and having no discount policy), each with the new tools or agents needed.

---

## Problem 11: Publish to GitHub

**Prompt:**
> Last problem, Problem Number 11. We are going to push the code to a public GitHub repository so that my graders can clone it and I am going to submit the repo URL to Canvas and also put it in output/github_url.txt.
>
> Do NOT push the real .env to the GitHub repo. Do include both database files under data/ (the original and the working copy) so that the graders can run the app easily.
>
> README should explain: copy original DB to the working copy when you need a clean run, start MCP server, start FastAPI backend, start the React board, reset the DB before a full three-ticket run.

**Follow-up:** None needed. Before pushing, the AI:
- scanned every file for the real Portkey key (0 hits);
- made `.mcp.json` use project-relative paths;
- wrote the README with the run steps and the full file tree;
- tested the README steps on a fresh clone: setup, DB copy, MCP smoke test, backend routes, and board build.

Repo: https://github.com/smalloy112321/campus-customs-multi-agent-ops (public, both `.db` files included, no `.env`).

---
