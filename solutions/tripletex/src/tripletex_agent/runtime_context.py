"""Per-request runtime context shared across the solver stack."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from .solve_logging import SolveEventLogger, SolveRequestContext

_CURRENT_REQUEST_CONTEXT: ContextVar[SolveRequestContext | None] = ContextVar(
    "tripletex_current_request_context",
    default=None,
)
_CURRENT_EVENT_LOGGER: ContextVar[SolveEventLogger | None] = ContextVar(
    "tripletex_current_event_logger",
    default=None,
)


def current_request_context() -> SolveRequestContext | None:
    return _CURRENT_REQUEST_CONTEXT.get()


def current_event_logger() -> SolveEventLogger | None:
    return _CURRENT_EVENT_LOGGER.get()


@contextmanager
def bind_runtime_context(
    *,
    request_context: SolveRequestContext,
    event_logger: SolveEventLogger | None,
) -> Iterator[None]:
    context_token: Token[SolveRequestContext | None] = _CURRENT_REQUEST_CONTEXT.set(request_context)
    logger_token: Token[SolveEventLogger | None] = _CURRENT_EVENT_LOGGER.set(event_logger)
    try:
        yield
    finally:
        _CURRENT_REQUEST_CONTEXT.reset(context_token)
        _CURRENT_EVENT_LOGGER.reset(logger_token)
