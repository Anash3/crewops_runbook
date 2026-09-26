"""Compose one application instance and its adapters."""

from dataclasses import dataclass

from crewops.application.services.approval_service import ApprovalService
from crewops.application.services.execution_service import RunbookExecutionService
from crewops.application.services.intake_service import IncidentIntakeService
from crewops.application.services.query_service import RunQueryService
from crewops.application.services.runbook_service import RunbookService
from crewops.core.contracts.event_sink import EventSink
from crewops.core.contracts.tool_executor import ToolExecutor
from crewops.infrastructure.config.settings import Settings, load_settings
from crewops.infrastructure.mcp.client import MCPClient
from crewops.infrastructure.observability.events import JsonlEventSink
from crewops.infrastructure.repositories.memory import InMemoryExecutionRepository
from crewops.orchestration.executor import RunbookExecution
from crewops.truefoundry.session import HarnessSessionManager


@dataclass
class ApplicationContainer:
    settings: Settings
    executions: InMemoryExecutionRepository[RunbookExecution]
    execution_service: RunbookExecutionService
    approval_service: ApprovalService
    query_service: RunQueryService
    intake_service: IncidentIntakeService
    harness_sessions: HarnessSessionManager


def create_application(
    settings: Settings | None = None,
    *,
    tool_executor: ToolExecutor | None = None,
    event_sink: EventSink | None = None,
) -> ApplicationContainer:
    settings = settings or load_settings()
    executions: InMemoryExecutionRepository[RunbookExecution] = InMemoryExecutionRepository()
    runbook_service = RunbookService()
    execution_service = RunbookExecutionService(
        runbook_service=runbook_service,
        tool_executor=tool_executor or MCPClient(settings.crewops_mcp_url, settings.mcp_api_key),
        repository=executions,
        event_sink=event_sink or JsonlEventSink(settings.event_log_path),
    )
    return ApplicationContainer(
        settings=settings,
        executions=executions,
        execution_service=execution_service,
        approval_service=ApprovalService(executions),
        query_service=RunQueryService(executions, runbook_service, settings.runbook_path),
        intake_service=IncidentIntakeService(settings.runbook_path.stem),
        harness_sessions=HarnessSessionManager(),
    )
