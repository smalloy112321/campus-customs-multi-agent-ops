"""Model and path configuration for the Campus Customs agent team.

Every agent uses one model: gpt-6-luna, routed through Portkey. MODEL_NAME is the
only place a model is named in this project, there is no override, and the team
refuses any response that comes back from a different model.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
OUTPUT_DIR = ROOT / "output"
AUDIT_PATH = OUTPUT_DIR / "audit_trail.json"
MCP_CONFIG_PATH = ROOT / ".mcp.json"
MCP_SERVER_NAME = "campus-customs"

MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
KEY_PLACEHOLDER = "your-portkey-api-key-here"  # the value shipped in .env.example

# Token budget. Sized at about 2x the largest real usage in the Problem 9 runs
# (73k tokens per ticket, 8.1k input on one request, 1.5k output on one response),
# so normal runs fit but a runaway delegation loop is stopped.
REQUEST_LIMIT_PER_TICKET = 60            # model requests across one ticket's whole delegation tree
TOTAL_TOKENS_PER_TICKET = 150_000        # input + output tokens across that tree
INPUT_TOKENS_PER_REQUEST = 20_000        # one model request's prompt + history
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4_000   # one model response

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def load_env() -> None:
    """Load the nearest .env: this project folder first, then each parent folder."""
    for folder in (ROOT, *ROOT.parents):
        if (folder / ".env").exists():
            load_dotenv(folder / ".env")
            return


def make_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey (Responses API, needed for tools + structured output)."""
    load_env()
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key or api_key == KEY_PLACEHOLDER:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your Portkey key.")
    return OpenAIResponsesModel(
        MODEL_NAME,
        provider=OpenAIProvider(api_key=api_key, base_url=PORTKEY_BASE_URL),
    )


def load_mcp_config() -> dict:
    """The campus-customs entry from .mcp.json, with project-relative paths made absolute
    so it works no matter which folder the backend is started from."""
    import json

    server = json.loads(MCP_CONFIG_PATH.read_text())["mcpServers"][MCP_SERVER_NAME]
    resolve = lambda p: str(ROOT / p) if not Path(p).is_absolute() and (ROOT / p).exists() else p  # noqa: E731
    return {"mcpServers": {MCP_SERVER_NAME: {
        **server,
        "command": resolve(server["command"]),
        "args": [resolve(a) for a in server.get("args", [])],
        "cwd": str(ROOT),
    }}}


def is_allowed_model(reported_name: str | None) -> bool:
    """True if a response's reported model is gpt-6-luna (allowing a dated suffix)."""
    return bool(reported_name) and (
        reported_name == MODEL_NAME or reported_name.startswith(MODEL_NAME + "-")
    )
