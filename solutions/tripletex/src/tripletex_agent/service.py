"""Service orchestration for the Tripletex solver endpoint."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import uuid4

from .client import TripletexClient
from .config import AppSettings
from .llm_executor import LLMApiExecutor
from .models import SolveRequest, SolveResponse, TripletexCredentials
from .runtime_context import bind_runtime_context
from .solve_logging import SolveEventLogger, SolveRequestContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SolveTrace:
    """Resolved trace metadata used through the lifetime of one solve call."""

    trace_id: str
    context: SolveRequestContext


class SolverService:
    """Coordinates LLM executor and Tripletex client setup."""

    def __init__(
        self,
        *,
        llm_executor: LLMApiExecutor,
        client_factory: Callable[[TripletexCredentials], TripletexClient],
        event_logger: SolveEventLogger | None = None,
    ) -> None:
        self._llm_executor = llm_executor
        self._client_factory = client_factory
        self._event_logger = event_logger

    async def solve(
        self,
        request: SolveRequest,
        *,
        context: SolveRequestContext | None = None,
    ) -> SolveResponse:
        trace = _resolve_trace(context)
        self._record_received(request=request, trace=trace)
        logger.info(
            "Received solve request trace_id=%s prompt=%r attachments=%s base_url=%s client=%s",
            trace.trace_id,
            request.prompt,
            [attachment.filename for attachment in request.files],
            request.tripletex_credentials.base_url,
            trace.context.client_host,
        )
        try:
            runtime_context = (
                bind_runtime_context(
                    request_context=trace.context,
                    event_logger=self._event_logger,
                )
                if self._event_logger is not None
                else nullcontext()
            )
            with runtime_context:
                async with self._client_factory(request.tripletex_credentials) as client:
                    result = await self._llm_executor.execute(
                        prompt=request.prompt,
                        attachments=request.files,
                        tripletex_client=client,
                    )
        except Exception as exc:
            self._record_failed(error=exc, trace=trace)
            logger.exception(
                "Solve request failed trace_id=%s prompt=%r",
                trace.trace_id,
                request.prompt,
            )
            raise

        if not result.completed:
            error_message = str(
                result.details.get("error", "LLM executor did not complete request")
            )
            self._record_failed(error=RuntimeError(error_message), trace=trace)
            logger.warning(
                "Solve request ended with internal failure trace_id=%s workflow=%s details=%s",
                trace.trace_id,
                result.name,
                json.dumps(result.details, ensure_ascii=False, default=str),
            )
            return SolveResponse(status="completed")

        self._record_completed(result=result, trace=trace)
        logger.info(
            "Solved request trace_id=%s workflow=%s operations=%s resources=%s details=%s",
            trace.trace_id,
            result.name,
            result.intended_operations,
            result.resource_ids,
            json.dumps(result.details, ensure_ascii=False, default=str),
        )

        return SolveResponse(status="completed")

    def _record_received(self, *, request: SolveRequest, trace: _SolveTrace) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_received(request=request, context=trace.context)

    def _record_completed(self, *, result, trace: _SolveTrace) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_completed(
            plan=None,
            workflow_name="unified_executor",
            result=result,
            context=trace.context,
        )

    def _record_failed(self, *, error: Exception, trace: _SolveTrace) -> None:
        if self._event_logger is None:
            return
        self._event_logger.record_failed(
            error=error,
            context=trace.context,
            plan=None,
            workflow_name="unified_executor",
        )


def build_default_service() -> SolverService:
    settings = AppSettings.load()

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set — the unified executor requires it"
        )

    executor = LLMApiExecutor(
        api_key=settings.anthropic_api_key,
        tool_model=settings.llm_tool_model,
        executor_model=settings.llm_executor_model,
    )
    logger.info(
        "Unified executor initialized: tool_model=%s executor_model=%s",
        settings.llm_tool_model, settings.llm_executor_model,
    )

    return SolverService(
        llm_executor=executor,
        client_factory=TripletexClient.from_credentials,
        event_logger=SolveEventLogger(settings.solve_event_log_path),
    )


def _resolve_trace(context: SolveRequestContext | None) -> _SolveTrace:
    if context is not None:
        return _SolveTrace(trace_id=context.trace_id, context=context)

    generated_context = SolveRequestContext(trace_id=str(uuid4()))
    return _SolveTrace(trace_id=generated_context.trace_id, context=generated_context)
