import os
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "ARIA MEHRA"
VERSION = "1.0"
OWNER = "Harshit"
DEFAULT_MODE = "normal"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_TIMEOUT_SECONDS = 30.0
MIN_API_KEY_LENGTH = 20


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if value is None:
        return default
    return value.strip().strip('"').strip("'")


OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _env("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL) or DEFAULT_OPENROUTER_MODEL
OPENROUTER_BASE_URL = _env("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL) or DEFAULT_OPENROUTER_BASE_URL
OPENROUTER_HTTP_REFERER = _env("OPENROUTER_HTTP_REFERER", "https://aria.local")
OPENROUTER_APP_TITLE = _env("OPENROUTER_APP_TITLE", APP_NAME)


def _timeout() -> float:
    raw = _env("OPENROUTER_TIMEOUT_SECONDS", str(DEFAULT_OPENROUTER_TIMEOUT_SECONDS))
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_OPENROUTER_TIMEOUT_SECONDS


OPENROUTER_TIMEOUT_SECONDS = _timeout()

TAVILY_API_KEY = _env("TAVILY_API_KEY")
DEFAULT_TAVILY_TIMEOUT_SECONDS = 15.0
DEFAULT_TAVILY_MAX_RESULTS = 5


def _tavily_timeout() -> float:
    raw = _env("TAVILY_TIMEOUT_SECONDS", str(DEFAULT_TAVILY_TIMEOUT_SECONDS))
    try:
        return max(1.0, min(float(raw), 60.0))
    except ValueError:
        return DEFAULT_TAVILY_TIMEOUT_SECONDS


def _tavily_max_results() -> int:
    raw = _env("TAVILY_MAX_RESULTS", str(DEFAULT_TAVILY_MAX_RESULTS))
    try:
        return max(1, min(int(raw), 10))
    except ValueError:
        return DEFAULT_TAVILY_MAX_RESULTS


TAVILY_TIMEOUT_SECONDS = _tavily_timeout()
TAVILY_MAX_RESULTS = _tavily_max_results()
