"""Local environment loading and settings for the Tripletex service."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .models import TripletexCredentials

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def configure_logging(log_level: str) -> None:
    """Ensure Tripletex agent logs are visible during local and tunnel runs."""

    agent_logger = logging.getLogger("tripletex_agent")
    if not agent_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        agent_logger.addHandler(handler)

    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    agent_logger.setLevel(resolved_level)
    agent_logger.propagate = False


def load_local_env(env_path: Path = DEFAULT_ENV_PATH) -> None:
    """Populate missing environment variables from a local .env file."""

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip().strip("'\"")

        os.environ.setdefault(normalized_key, normalized_value)


@dataclass(frozen=True)
class AppSettings:
    """Resolved runtime settings for local development and sandbox checks."""

    tripletex_base_url: str | None
    tripletex_session_token: str | None
    anthropic_api_key: str | None
    llm_tool_model: str
    llm_executor_model: str
    host: str
    port: int
    log_level: str
    solve_event_log_path: Path

    @classmethod
    def load(cls) -> AppSettings:
        load_local_env()
        configured_log_path = os.getenv("SOLVE_EVENT_LOG_PATH")
        return cls(
            tripletex_base_url=os.getenv("TRIPLETEX_BASE_URL"),
            tripletex_session_token=os.getenv("TRIPLETEX_SESSION_TOKEN"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            llm_tool_model=os.getenv(
                "LLM_TOOL_MODEL", "claude-haiku-4-5-20251001"
            ),
            llm_executor_model=os.getenv(
                "LLM_EXECUTOR_MODEL", "claude-sonnet-4-6"
            ),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            solve_event_log_path=Path(configured_log_path)
            if configured_log_path
            else PROJECT_ROOT / "logs" / "solve-events.jsonl",
        )

    def tripletex_credentials(self) -> TripletexCredentials:
        if not self.tripletex_base_url or not self.tripletex_session_token:
            raise ValueError(
                "TRIPLETEX_BASE_URL and TRIPLETEX_SESSION_TOKEN must be set "
                "in the environment or .env"
            )

        return TripletexCredentials(
            base_url=self.tripletex_base_url,
            session_token=self.tripletex_session_token,
        )
