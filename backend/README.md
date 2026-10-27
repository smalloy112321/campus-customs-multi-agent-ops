# Campus Customs Backend

This folder holds the FastAPI routes the React dashboard calls, plus the PydanticAI agent team (Boss, Inventory, Accounting, Facilities, Customer Service). Every agent uses `gpt-6-luna` through Portkey (`PORTKEY_API_KEY` from `.env`). All shop data goes through the campus-customs MCP server (`../.mcp.json`).

## Start

```bash
cd backend
uvicorn main:app --reload --port 8000        # with the project venv active
# or: ../.venv/bin/python -m uvicorn main:app --reload --port 8000
```

Before restarting, check for an orphan server with `lsof -i :8000`. When stopping, stop the whole uvicorn process tree: the reloader and its worker.

`--reload` only watches `backend/`. After editing `mcp_server/server.py`, restart the server so the routes' MCP connection picks up the change. Agent runs always start a fresh MCP server.

## Routes

Listed with one line each in `../output/harness.md`. Interactive docs are at http://localhost:8000/docs.

## Files

- `main.py`: FastAPI routes
- `team.py`: MCP connection and the agent loop, writing to `../output/audit_trail.json`
- `agents/`: one file per agent
- `prompts/`: one prompt per agent
- `models.py`: data types
- `efficiency.py`: scores a run against the plan in `../output/desk_tickets.html`
- `audit.py`: append-only audit trail
- `config.py`: model and paths
- `run_tickets.py`: command-line runner
