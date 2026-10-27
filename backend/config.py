"""Model and path configuration for the Campus Customs agent team.

Every agent uses one model: gpt-6-luna, routed through Portkey. MODEL_NAME is the
only place a model is named in this project, there is no override, and the team
refuses any response that comes back from a different model.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.fallback import FallbackModel
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

# Token budget. Sized from the real Problem 9 runs (73k tokens per ticket, 8.1k input on one
# request) so normal runs fit but a runaway delegation loop is stopped.
# A per-response output cap (max_tokens 4k) was tried and removed: in test reruns after the
# Problem 9 run, the Boss's final structured answer used the whole 4k on hidden reasoning and the
# run stopped with an error. Token limits are only checked after a response returns, so a stuck
# request gets a hard deadline instead, and is retried on the same model (MODEL_ATTEMPTS).
REQUEST_LIMIT_PER_TICKET = 60            # model requests across one ticket's whole delegation tree
TOTAL_TOKENS_PER_TICKET = 150_000        # input + output tokens across that tree
INPUT_TOKENS_PER_REQUEST = 20_000        # one model request's prompt + history
REQUEST_TIMEOUT_SECONDS = 90             # deadline for one attempt at one model request
MODEL_ATTEMPTS = 3                       # a timed-out or failed request is retried on gpt-6-luna

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def load_env() -> None:
    """Load the nearest .env: this project folder first, then each parent folder."""
    for folder in (ROOT, *ROOT.parents):
        if (folder / ".env").exists():
            load_dotenv(folder / ".env")
            return


def _luna(api_key: str) -> OpenAIResponsesModel:
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(api_key=api_key, base_url=PORTKEY_BASE_URL))


def make_model() -> FallbackModel:
    """gpt-6-luna through Portkey (Responses API, needed for tools + structured output).

    Wrapped so a request that times out or errors is retried, up to MODEL_ATTEMPTS times in
    total. Every attempt is gpt-6-luna; no other model is ever involved.
    """
    load_env()
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key or api_key == KEY_PLACEHOLDER:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your Portkey key.")
    attempts = [_luna(api_key) for _ in range(MODEL_ATTEMPTS)]
    return FallbackModel(attempts[0], *attempts[1:])


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
