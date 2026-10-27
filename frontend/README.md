# Campus Customs Operations Desk (frontend)

A React + Vite + TypeScript dashboard where you watch the agent team work each ticket, approve payments, and see the checking balance drop. It calls the FastAPI backend at `http://localhost:8000` (set `VITE_API_BASE` to change it). The design choices are explained in `../output/design.md`.

## Run

```bash
# 1. backend (from backend/)
uvicorn main:app --reload --port 8000
# 2. board (from frontend/)
npm install
npm run dev        # http://localhost:5173 (port pinned; the backend's CORS expects it)
```

## Files

- `src/App.tsx`: polls the backend (every 5 s, or 1.5 s while a run is live)
- `src/api.ts`: one function per backend route
- `src/agents.ts`: agent names, colors, labels and helpers
- `src/components/`:
  - `Header`: logo and checking balance
  - `Hero`: fans photo and counters
  - `TicketList`
  - `TicketWorkspace`
  - `AgentRoster`
  - `ActivityFeed`
  - `ApprovalCard`
  - `SummaryPanel`
  - `EfficiencyPanel`
- `src/assets/hero-yale-fans.jpg`, `src/components/Logo.tsx` and `public/favicon.svg` come from the Campus Customs store (Homework 4).
