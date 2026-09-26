"""Read models for the operator UI, built only from execution state and tool outputs."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crewops.application.services.runbook_service import RunbookService
from crewops.core.contracts.repositories import ExecutionRepository
from crewops.core.enums.execution_status import ExecutionState
from crewops.orchestration.executor import RunbookExecution
from crewops.orchestration.narration import checks_sentence, observe_and_decide


class RunQueryService:
    def __init__(
        self,
        repository: ExecutionRepository[RunbookExecution],
        runbook_service: RunbookService,
        runbook_path: Path,
    ) -> None:
        self.repository = repository
        self.runbook_service = runbook_service
        self.runbook_path = runbook_path

    def get(self, run_id: str) -> RunbookExecution | None:
        return self.repository.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        return sorted(
            (self.summary(run) for run in self.repository.all()),
            key=lambda item: item["started_at"] or "",
            reverse=True,
        )

    def summary(self, run: RunbookExecution) -> dict[str, Any]:
        flight = run.context.get("get_flight") or {}
        return {
            "run_id": run.execution_id,
            "case_id": run.context.get("case_id"),
            "runbook_id": run.runbook_id,
            "runbook_name": run.runbook.name,
            "runbook_version": run.runbook.version,
            "flight_id": flight.get("flight_id", run.context.get("flight_id")),
            "issue": run.context.get("issue"),
            "status": run.state.value,
            "started_at": run.events[0]["timestamp"] if run.events else None,
            "updated_at": run.events[-1]["timestamp"] if run.events else None,
            "completed_steps": sum(
                item.get("status") == "COMPLETED" for item in run.step_results
            ),
            "total_steps": len(run.runbook.steps),
        }

    @staticmethod
    def public_trace_entry(event: dict[str, Any], index: int) -> dict[str, Any] | None:
        """Small, replayable entry for the live Plan → Act → Observe view."""
        kind = event.get("event")
        entry_type = {
            "RUNBOOK_SELECTED": "ROUTE",
            "REASONING_SUMMARY": "PLAN",
            "TOOL_CALLED": "ACT",
            "OBSERVATION": "OBSERVE",
            "APPROVAL_REQUESTED": "GATE",
            "APPROVAL_RECEIVED": "APPROVAL",
            "STEP_FAILED": "ERROR",
            "STEP_SKIPPED": "SKIP",
            "RUN_COMPLETED": "DONE",
            "RUN_REJECTED": "DONE",
            "RUN_BLOCKED": "DONE",
            "RUN_FAILED": "DONE",
        }.get(kind)
        if entry_type is None:
            return None
        message = {
            "RUNBOOK_SELECTED": event.get("selection_reason"),
            "REASONING_SUMMARY": event.get("message"),
            "OBSERVATION": event.get("message"),
            "APPROVAL_REQUESTED": "The roster tool call is blocked until a human approves this exact action.",
            "APPROVAL_RECEIVED": "The human approved the pending action." if event.get("decision") == "approve" else "The human rejected the pending action.",
            "STEP_FAILED": event.get("reason"),
            "STEP_SKIPPED": event.get("reason"),
            "RUN_COMPLETED": "Runbook complete. Final verification is available below.",
            "RUN_REJECTED": "Run stopped after human rejection.",
            "RUN_BLOCKED": "Run stopped at a safety boundary.",
            "RUN_FAILED": "Run stopped after a tool failure.",
        }.get(kind)
        if kind == "TOOL_CALLED":
            message = f"Calling {event.get('tool')} with the resolved runbook arguments."
        return {
            "id": index,
            "type": entry_type,
            "step_id": event.get("step_id"),
            "timestamp": event.get("timestamp"),
            "message": message,
            "tool": event.get("tool") if kind == "TOOL_CALLED" else None,
            "arguments": event.get("arguments") if kind == "TOOL_CALLED" else None,
            "checks": event.get("checks") if kind == "OBSERVATION" else None,
        }

    def detail(self, run: RunbookExecution) -> dict[str, Any]:
        flight = run.context.get("get_flight") or {}
        roster = run.context.get("get_roster") or []
        constraints = (run.context.get("identify_constraint") or {}).get("constraints") or []
        constraint = constraints[0] if constraints else {}
        reserve = run.context.get("search_reserve") or {}
        candidate = run.context.get("validate_candidate") or {}
        simulation = run.context.get("simulate_change") or {}
        verification = run.context.get("verify") or {}
        applied = run.context.get("apply_change") or {}
        completed = run.to_dict() if run.state == ExecutionState.COMPLETED else None

        projected = constraint.get("projected_duty_minutes")
        maximum = constraint.get("max_allowed_minutes")
        over = constraint.get("over_limit_minutes")
        impact = None
        if all(isinstance(value, (int, float)) for value in (projected, maximum, over)):
            impact = (
                f"Projected duty is {projected} minutes, {over} minutes over "
                f"the recorded {maximum}-minute limit."
            )
        elif constraint:
            impact = constraint.get("reason")

        current_ids = [
            member.get("crew_id") for member in roster if isinstance(member, dict)
        ]
        removed = simulation.get("proposed_removal", constraint.get("crew_id"))
        replacement = simulation.get("proposed_replacement", candidate.get("crew_id"))
        proposed_ids = [
            replacement if crew_id == removed else crew_id for crew_id in current_ids
        ] if simulation.get("safe") is True and replacement else []

        result_by_id = {item["step_id"]: item for item in run.step_results}
        steps = []
        for index, step in enumerate(run.runbook.steps):
            result = result_by_id.get(step.id)
            if result:
                status = result["status"]
            elif index == run.step_index:
                status = (
                    "WAITING_FOR_APPROVAL"
                    if run.state == ExecutionState.WAITING_FOR_APPROVAL
                    else "RUNNING" if run.state in {ExecutionState.RUNNING, ExecutionState.APPROVED}
                    else "PENDING"
                )
            else:
                status = "PENDING"
            step_result = result.get("result") if result else None
            observation, next_decision = observe_and_decide(step.id, step_result)
            if observation and step.id in {"validate_candidate", "simulate_change"}:
                observation += " " + checks_sentence(step.id, step_result)
            pending_arguments = (
                run.pending_approval.arguments
                if status == "WAITING_FOR_APPROVAL" and run.pending_approval
                else None
            )
            steps.append({
                "id": step.id,
                "description": step.description,
                "tool": step.tool,
                "destructive": step.destructive,
                "status": status,
                "arguments": result.get("arguments") if result else pending_arguments,
                "result": step_result,
                "reason": result.get("reason") if result else None,
                "observation": observation,
                "next_decision": next_decision,
            })

        approval = None
        pending = run.pending_approval
        if run.state == ExecutionState.WAITING_FOR_APPROVAL and pending:
            approval = {
                "approval_id": pending.approval_id,
                "action_hash": pending.action_hash,
                "expires_at": pending.expires_at.isoformat(),
                "run_id": pending.run_id,
                "runbook_id": pending.runbook_id,
                "step_id": pending.step_id,
                "tool": pending.tool,
                "arguments": pending.arguments,
                "proposal": run.to_dict()["approval_required"]["proposal"],
            }

        return {
            **self.summary(run),
            "description": run.runbook.description,
            "selection_reason": run.context.get("selection_reason"),
            "current_step": (
                run.runbook.steps[run.step_index].id
                if run.step_index < len(run.runbook.steps) else None
            ),
            "steps": steps,
            "brief": {
                "where": {
                    "flight_id": flight.get("flight_id", run.context.get("flight_id")),
                    "origin": flight.get("origin"),
                    "destination": flight.get("destination"),
                    "affected_crew_id": constraint.get("crew_id"),
                    "affected_crew_name": constraint.get("name"),
                },
                "why": {
                    "delay_minutes": flight.get("delay_minutes"),
                    "constraint": constraint or None,
                    "rule": (run.context.get("identify_constraint") or {}).get("rule"),
                },
                "so_what": impact,
                "proposed_action": {
                    "remove_crew_id": removed,
                    "replacement_crew_id": replacement,
                    "candidate_name": candidate.get("name"),
                },
                "validation": {
                    "reserve_found": bool(reserve.get("candidates")),
                    "candidate_valid": candidate.get("valid"),
                    "checks": candidate.get("checks") or {},
                    "simulation_safe": simulation.get("safe"),
                    "simulation_checks": simulation.get("checks") or {},
                },
            },
            "simulation": {
                "available": bool(simulation),
                "safe": simulation.get("safe"),
                "read_only": simulation.get("read_only"),
                "issues": simulation.get("issues") or [],
                "current_roster": current_ids,
                "proposed_roster": proposed_ids,
                "remove_crew_id": removed,
                "replacement_crew_id": replacement,
            },
            "approval": approval,
            "approval_status": run.approval_status,
            "action": applied or None,
            "verification": verification or None,
            "report": completed.get("report") if completed else None,
            "failure": getattr(run, "failure", None),
            "events_count": len(run.events),
            "trace": [entry for index, event in enumerate(run.events, 1) if (entry := self.public_trace_entry(event, index)) is not None],
        }

    def approvals(self) -> list[dict[str, Any]]:
        return [
            {"run": self.summary(run), "approval": self.detail(run)["approval"]}
            for run in self.repository.all()
            if run.state == ExecutionState.WAITING_FOR_APPROVAL and run.pending_approval
        ]

    def runbook(self) -> dict[str, Any]:
        runbook = self.runbook_service.load(self.runbook_path)
        return {
            "id": self.runbook_path.stem,
            "name": runbook.name,
            "version": runbook.version,
            "description": runbook.description,
            "steps": [step.model_dump() for step in runbook.steps],
        }

    def overview(self) -> dict[str, Any]:
        runs = self.list_runs()
        today = datetime.now(timezone.utc).date().isoformat()
        return {
            "active_runs": sum(item["status"] in {"RUNNING", "APPROVED"} for item in runs),
            "awaiting_approval": sum(item["status"] == "WAITING_FOR_APPROVAL" for item in runs),
            "completed_today": sum(
                item["status"] == "COMPLETED" and (item["updated_at"] or "").startswith(today)
                for item in runs
            ),
            "recent_runs": runs[:8],
        }
