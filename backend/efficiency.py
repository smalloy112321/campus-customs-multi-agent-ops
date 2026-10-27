"""Efficiency score for a ticket run, measured against the plan in output/desk_tickets.html.

The plan (expected specialists, required/optional tools per agent, budgets) and the
penalty weights live in one JSON block inside desk_tickets.html (id="ticket-plans").
That page's meter and this module both read it, so they score runs the same way.

Start at 100 and subtract the weighted penalties; 85+ is Efficient, 60-84 is
Acceptable, below 60 Needs tuning (thresholds also come from the JSON block).
"""

from __future__ import annotations

import json
import re
from collections import Counter

from backend.config import OUTPUT_DIR

PLANS_HTML = OUTPUT_DIR / "desk_tickets.html"
NON_MCP_TOOLS = {"delegate", "final_result"}
_BLOCK = re.compile(r'<script type="application/json" id="ticket-plans">(.*?)</script>', re.DOTALL)


def load_plans() -> dict:
    match = _BLOCK.search(PLANS_HTML.read_text())
    if not match:
        raise RuntimeError(f"No ticket-plans JSON block in {PLANS_HTML}")
    return json.loads(match.group(1))


def _rating(score: int, thresholds: dict) -> str:
    if score >= thresholds["efficient"]:
        return "Efficient"
    if score >= thresholds["acceptable"]:
        return "Acceptable"
    return "Needs tuning"


def measure(ticket_id: int, entries: list[dict]) -> dict | None:
    """Score the latest run for ticket_id in the audit trail. None if it never ran."""
    data = load_plans()
    plan = data["plans"].get(str(ticket_id))
    if plan is None:
        return None
    w = data["weights"]
    mine = [e for e in entries
            if e.get("ticket_id") == ticket_id and str(e.get("run_id", "")).startswith(f"ticket-{ticket_id}-")]
    if not mine:
        return None
    run_id = mine[-1]["run_id"]
    run = [e for e in mine if e["run_id"] == run_id]

    agents = {e["agent"] for e in run if e["event"] == "run_start"}
    solo_date_turns = Counter()  # turns where an agent called only get_shop_today
    planned = [a for a in plan["tools"] if a != "boss"]
    specialists = sorted(a for a in agents if a != "boss")
    delegations, tool_calls, seen = [], [], Counter()
    model_requests = 0
    for e in run:
        if e["event"] != "model_response":
            continue
        model_requests += 1
        called = [p["tool_name"] for p in e["detail"].get("parts", []) if p.get("kind") == "tool-call"]
        if called == ["get_shop_today"]:
            solo_date_turns[e["agent"]] += 1
        for p in e["detail"].get("parts", []):
            if p.get("kind") != "tool-call":
                continue
            if p["tool_name"] == "delegate":
                delegations.append(f"{e['agent']} -> {(p.get('args') or {}).get('to')}")
            if p["tool_name"] in NON_MCP_TOOLS:
                continue
            tool_calls.append((e["agent"], p["tool_name"]))
            seen[(e["agent"], p["tool_name"], json.dumps(p.get("args"), sort_keys=True))] += 1

    extra_specialists = [a for a in specialists if a not in planned]
    missing_specialists = [a for a in planned if a not in agents]
    unexpected = [f"{a}: {t}" for a, t in tool_calls
                  if a not in plan["tools"] or t not in plan["tools"][a]["required"] + plan["tools"][a]["optional"]]
    missing_tools = [f"{a}: {t}" for a, spec in plan["tools"].items() for t in spec["required"]
                     if (a, t) not in tool_calls]
    duplicate_extra = sum(n - 1 for n in seen.values() if n > 1)
    budget = plan["budget"]

    penalties = {
        "extra_specialist": len(extra_specialists) * w["extra_specialist"],
        "missing_specialist": len(missing_specialists) * w["missing_specialist"],
        "delegation_over": max(0, len(delegations) - budget["delegations"]) * w["delegation_over"],
        "missing_required_tool": len(missing_tools) * w["missing_required_tool"],
        "unexpected_tool_call": len(unexpected) * w["unexpected_tool_call"],
        "duplicate_call": duplicate_extra * w["duplicate_call"],
        "tool_call_over_budget": max(0, len(tool_calls) - budget["toolCalls"]) * w["tool_call_over_budget"],
        "model_request_over_budget": max(0, model_requests - budget["modelRequests"]) * w["model_request_over_budget"],
    }
    score = max(0, 100 - sum(penalties.values()))
    final = next((e for e in reversed(run) if e["event"] == "run_end" and e["agent"] == "boss"), None)
    repeated = [{"agent": a, "tool": t, "extra": n - 1} for (a, t, _), n in seen.items() if n > 1]
    calls_by_agent = Counter(a for a, _ in tool_calls)
    # Optional lookups beyond each agent's required tools (the shop date is tipped separately).
    optional_by_agent: dict[str, list[str]] = {}
    for a, t in tool_calls:
        if a in plan["tools"] and t in plan["tools"][a]["optional"] and t != "get_shop_today":
            optional_by_agent.setdefault(a, []).append(t)
    return {
        "score": score,
        "rating": _rating(score, data["ratings"]),
        "run_id": run_id,
        "specialists": specialists,
        "planned_specialists": planned,
        "delegations": delegations,
        "mcp_tool_calls": len(tool_calls),
        "model_requests": model_requests,
        "budget": budget,
        "extra_specialists": extra_specialists,
        "missing_specialists": missing_specialists,
        "missing_required_tools": missing_tools,
        "unexpected_tool_calls": unexpected,
        "repeated_calls": duplicate_extra,
        "final_status": (final or {}).get("detail", {}).get("output", {}).get("final_status"),
        "penalties": {k: v for k, v in penalties.items() if v},
        "calls_by_agent": dict(calls_by_agent),
        "improvements": _improvements(plan, penalties, extra_specialists, missing_specialists, missing_tools,
                                      unexpected, repeated, optional_by_agent, solo_date_turns,
                                      len(tool_calls), model_requests),
    }


LABEL = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service"}


def _improvements(plan, penalties, extra, missing, missing_tools, unexpected, repeated,
                  optional_by_agent, solo_date_turns, n_tools, n_requests) -> list[dict]:
    """Concrete tips for next time, each tied to a deduction it would win back."""
    tips: list[dict] = []
    for a in extra:
        tips.append({"points": penalties["extra_specialist"] // max(len(extra), 1),
                     "tip": f"Skip {LABEL.get(a, a)} on this kind of ticket; the plan doesn't need it. "
                            "Tighten the Boss prompt's routing table."})
    for a in missing:
        tips.append({"points": penalties["missing_specialist"] // max(len(missing), 1),
                     "tip": f"{LABEL.get(a, a)} never ran. The Boss should delegate to it; its answer is part of the plan."})
    def who(item: str) -> tuple[str, str]:
        agent, tool = item.split(": ", 1)
        return LABEL.get(agent, agent), tool
    for m in missing_tools:
        a, t = who(m)
        tips.append({"points": 10, "tip": f"{a} never called {t}. Name that tool in the delegation task so it isn't skipped."})
    for u in unexpected:
        a, t = who(u)
        tips.append({"points": 5, "tip": f"{a} called {t}, which the plan doesn't expect. Remove it from that agent's toolset or prompt for this ticket type."})
    for r in repeated:
        tips.append({"points": r["extra"] * 3,
                     "tip": f"{LABEL.get(r['agent'], r['agent'])} called {r['tool']} again with the same arguments. "
                            "Reuse the first answer instead of asking twice."})
    if penalties["tool_call_over_budget"] or penalties["model_request_over_budget"]:
        if optional_by_agent:
            a, tools = max(optional_by_agent.items(), key=lambda kv: len(kv[1]))
            if len(tools) >= 2:
                listed = ", ".join(sorted(set(tools)))
                why = ("its specialists already return sourced facts, so spot-check only the money figures"
                       if a == "boss" else
                       "put those facts in the delegation task so it doesn't fetch them again")
                tips.append({"points": penalties["tool_call_over_budget"],
                             "tip": f"{LABEL.get(a, a)} made {len(tools)} extra lookups ({listed}); {why}."})
        solo = sum(solo_date_turns.values())
        if solo >= 2:
            tips.append({"points": penalties["model_request_over_budget"],
                         "tip": f"{solo} turns were spent only on get_shop_today. Put the shop date in each delegation "
                                "task, or batch it with the first lookups, to save a model request per agent."})
    if not tips:
        tips.append({"points": 0, "tip": "On plan: right specialists, required tools, within budget. Nothing to trim."})
    return tips
