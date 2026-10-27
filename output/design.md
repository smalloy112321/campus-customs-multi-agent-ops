# Dashboard Design: Campus Customs Operations Desk

The board in `frontend/` (React + Vite + TypeScript) is where a human watches the five agents work a ticket and signs off on money. It talks to the FastAPI backend at `http://localhost:8000`. Start it with `npm run dev` and open http://localhost:5173.

## What we chose, and why

### Brand: borrowed from the Campus Customs store (Homework 4)
| Element | Choice | Why |
|---|---|---|
| **Logo** | The felt-pennant logo we created for the store ("CAMPUS CUSTOMS · EST. 1975"), reused as the same inline SVG component (`Logo.tsx`), plus the pennant favicon. | The ops desk should feel like the back office of the same shop, not a generic admin tool. |
| **Hero photo** | The home-screen photo of Yale fans with the **LET'S GO YALE** banner (`hero-yale-fans.jpg`). | It's the most recognizable image from the store, and it reminds the operator who the work is for. |
| **Colors** | Yale blue `#00356b`, pennant cream `#f6f1e6`, pennant shadow blue `#6c8ebf`. Gold (`#b8860b` for accents, `#8a6408` for text and buttons) is used **only** for money that needs a human. | The store's palette, plus one extra color with one job: if it's gold, it's waiting for you. |
| **Type** | Cormorant Garamond for headings, Lato for reading, Graduate (the pennant font) for ticket numbers and agent initials. | The same Ivy pairing as the store. Graduate ties the small details back to the logo. |

### Layout
- **Header (cream band):** the logo, "Operations Desk", and the **checking balance** as the biggest number on the page. Under it: what's pending and what would be left if everything were approved. There is also a "to approve" count and a **Reset shop** button, which asks for confirmation and is disabled during a run.
- **Hero strip:** the fans photo under a left-to-right navy gradient, with the headline "Five agents run the shop. You sign off on the money." and three live counters: Open, Needs you, Resolved. It is shorter than the store's hero, because this is a work tool.
- **Left rail: "The board".** One card per ticket: number, type, subject, requester, a status pill, and an **⚡ efficiency badge** once it's resolved. The selected card gets a navy edge.
- **Workspace (right):**
  1. **Ticket header**: subject, requester, SKU/size/qty, the customer's note, the status, and **Run agent team**.
  2. **Agent roster**: five cards (Boss, Inventory, Accounting, Facilities, Customer Service). Each shows *Not called*, *Working…* (pulsing ring) or *Reported back*, so you can see at a glance how few specialists a ticket used.
  3. **Approval card (gold)**: appears only when an agent prepared a payment or purchase order. It shows what it is, the amount, the payee, the agent's reason, who prepared it, and **checking after** this payment. It warns in red if cash would go negative. You type your name once (remembered) and click **Approve $X** or **Reject**.
  4. **Agent activity** (live feed): a timeline with one color per agent. Delegations are indented. Tool calls are written in plain English ("counted stock, checked the vendor") with the exact MCP tool names as chips. Tool results fold away under "N tools answered". It polls every 1.2 s while running and auto-scrolls.
  5. **What the team did**: the Boss's call as a pull-quote, one line per specialist, and "On the board" (payment requests, POs, drafts marked **draft · not sent**, expandable to read).
  6. **Efficiency**: a ring gauge (green, gold or red) with the score, the specialists used, meters for delegations, tool calls and model requests against the plan's budget, and **"How to do better next time"**: concrete tips, each with the points it would win back.

### Agent identity
| Agent | Color | Note |
|---|---|---|
| The Boss | Yale blue `#00356b` | The brand color, because the Boss speaks for the shop |
| Inventory | Teal `#1f6f78` | |
| Accounting | Green `#2e6b3a` | Money-adjacent, but not the gold used for "needs you" |
| Facilities | Brown `#8a5a12` | The building and the lease |
| Customer Service | Purple `#6b3fa0` | The purple of the **BOOLA BOOLA** sign in the hero photo |

The same color is used for the roster avatar, the feed dot and name, the summary line and the efficiency chip, so you can follow one agent across the whole page.

## Changes we made while building, and why

| Change | Why it makes the desk friendlier |
|---|---|
| **The store's storefront hero became a short strip with live counters.** | An operator needs the work above the fold. The photo keeps the brand, and the counters answer "is anything waiting for me?" at once. |
| **Money gets its own color (gold) and its own card.** | Approvals are the one thing only a human can do. They shouldn't hide in the feed. |
| **"Checking after: $X" on every approval, with a red warning if negative.** | You see the consequence before you click, and the pay tool's refusal is never a surprise. |
| **The approver's name is required and remembered.** | Every payment records who approved it (`payments.approved_by`), with no anonymous clicks and no retyping. |
| **Plain-English tool names, with the raw MCP names as chips.** | Readable for a manager, still exact enough for an audit. |
| **Tool results are folded by default.** | The feed tells the story; the raw JSON is one click away instead of drowning the timeline. |
| **Feed titles: agent name and action kept together, time on the right.** | The first version spread the name, the action and the time across the row, which was hard to scan. |
| **The board only shows work since the last reset.** | After a reset, old runs described a shop that no longer exists ("Reported back" on a fresh ticket). The audit file is still append-only; the board just scopes its view (`include_history=true` shows everything). |
| **A ticket is marked resolved when its run finishes**, unless a payment is waiting on you, in which case approving the last payment resolves it. | It matches the brief ("mark resolved when the run finishes") without ever resolving past a pending approval. |
| **Run is disabled while another ticket runs or a payment is pending.** | Tickets share one checking account and run one at a time; this prevents double-work and accidental overlaps. |
| **Efficiency shows *why* and *how to improve*, not just a number.** | A score alone doesn't help next time. Tips tie each deduction to a fix (for example "put the shop date in each delegation task"). |
| **Delegations are shown as "The Boss → Inventory".** | Agent names instead of internal ids. |

## Accessibility and states
- Contrast: navy on white and cream, and white on the darkened photo, all pass WCAG AA. The first gold (`#b8860b`) was only about 3.3:1 with white text, so buttons and gold labels use `#8a6408` (about 5.4:1). The brighter gold stays for borders and bars only.
- Keyboard: real `<button>`s, a skip link to the workspace, visible yellow focus rings, and `aria-current` on the selected ticket.
- Screen readers: `aria-live` on the workspace and the cash card, plus descriptive alt text on the hero, the gauge and the score badges.
- Clear states: loading text, "No run yet" empty states, a "Live" pill and typing dots while agents work, and red banners if the backend can't be reached ("Is uvicorn running?") or a run errors.

## Next polish round (your feedback goes here)
These are candidates I'll work through once you've looked at it:
- **Your feedback:** _(to fill in)_
- **Approve button should never fail silently.** Testing showed the name requirement was easy to miss: clicking Approve with an empty "Approving as" field only showed a small red line. Disable Approve until a name is entered, with a visible prompt. Also show a clear "backend offline" state right on the approval card.
- Collapse the feed to one line per agent turn, with an "expand" option, for long runs.
- Toast confirmations after Approve, Reject and Reset, with the new balance animating down.
- A compact "Cash" view (payments made, what's pending) to feed the empty Cash tab from Problem 6.
- Tighter mobile layout for the roster and the approval card.
