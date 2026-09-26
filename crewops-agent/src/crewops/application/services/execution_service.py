"""Execute a validated runbook and retain its state across human approval."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from crewops.application.services.runbook_service import RunbookService
from crewops.core.contracts.event_sink import EventSink
from crewops.core.contracts.repositories import ExecutionRepository
from crewops.core.contracts.tool_executor import ToolExecutor
from crewops.core.enums.execution_status import ExecutionState
from crewops.orchestration.executor import RunbookExecution


ProgressCallback = Callable[[float, float | None, str | None], Awaitable[None]]


class RunbookExecutionService:
    def __init__(
        self,
        runbook_service: RunbookService,
        tool_executor: ToolExecutor,
        repository: ExecutionRepository[RunbookExecution],
        event_sink: EventSink,
    ) -> None:
        self.runbook_service = runbook_service
        self.tool_executor = tool_executor
        self.repository = repository
        self.event_sink = event_sink

    async def execute(
        self,
        runbook_path: Path,
        input_data: dict[str, Any],
        report_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        execution = self.start(runbook_path, input_data)
        progress_task = (
            asyncio.create_task(self._report_approval_progress(execution, report_progress))
            if report_progress else None
        )
        try:
            # A disconnected MCP caller must not cancel a run awaiting approval.
            return await asyncio.shield(execution.runner_task)
        finally:
            if progress_task:
                progress_task.cancel()
                await asyncio.gather(progress_task, return_exceptions=True)

    def start(self, runbook_path: Path, input_data: dict[str, Any]) -> RunbookExecution:
        """Start a run and return its state immediately for the operator UI."""
        runbook = self.runbook_service.load(runbook_path)
        execution = RunbookExecution(
            runbook,
            self.tool_executor,
            self.event_sink,
            inputs=input_data,
            runbook_id=runbook_path.stem,
        )
        self.repository.save(execution)
        execution.runner_task = asyncio.create_task(self._drive(execution))
        return execution

    async def _drive(self, execution: RunbookExecution) -> dict[str, Any]:
        result = await execution.run()
        while execution.state == ExecutionState.WAITING_FOR_APPROVAL:
            await execution.approval_event.wait()
            execution.approval_event.clear()
            if execution.state == ExecutionState.APPROVED:
                result = await execution.run()
            else:
                result = execution.to_dict()
        return result

    async def _report_approval_progress(
        self,
        execution: RunbookExecution,
        report_progress: ProgressCallback,
    ) -> None:
        heartbeat = 0
        while not execution.runner_task or not execution.runner_task.done():
            await asyncio.sleep(15)
            if execution.state != ExecutionState.WAITING_FOR_APPROVAL:
                continue
            heartbeat += 1
            try:
                pending = execution.pending_approval
                await report_progress(
                    float(heartbeat),
                    None,
                    f"Waiting for approval of {pending.tool if pending else 'action'}",
                )
            except Exception:
                # Progress never controls the approval gate.
                continue
