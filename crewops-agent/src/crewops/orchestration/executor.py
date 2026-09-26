"""Run one human-authored procedure with a deterministic approval gate."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from crewops.core.contracts.event_sink import EventSink
from crewops.core.contracts.tool_executor import ToolExecutor
from crewops.core.domain.approval import Approval
from crewops.core.domain.execution import ExecutionContext
from crewops.core.domain.runbook import Runbook, RunbookStep
from crewops.core.enums.execution_status import ExecutionState
from crewops.core.exceptions import ToolTimeoutError, ToolUnavailableError
from crewops.orchestration.context import condition_is_true, issues_text, resolve_value
from crewops.orchestration.narration import check_details, observe_and_decide, plan_for_step


class RunbookExecution:
    """Executor with an engine-owned approval gate for destructive steps."""

    READ_ONLY_TOOLS = {
        "flight_get",
        "flight_roster",
        "duty_clock_get",
        "identify_constraint",
        "reserve_search",
        "validate_candidate",
        "simulate_roster_change",
        "verify_roster",
    }
    DESTRUCTIVE_TOOLS = {"roster_apply_change"}

    def __init__(
        self,
        runbook: Runbook,
        tool_executor: ToolExecutor,
        event_sink: EventSink,
        inputs: dict[str, Any] | None = None,
        runbook_id: str = "runbook",
    ) -> None:
        self.runbook = runbook
        self.runbook_id = runbook_id
        self.execution_id = uuid.uuid4().hex
        self.tool_executor = tool_executor
        self.event_sink = event_sink
        self.context: dict[str, Any] = dict(inputs or {})
        self.step_results: list[dict[str, Any]] = []
        self.execution_context = ExecutionContext(input=dict(inputs or {}))
        self.event_log_path = event_sink.path
        self.events: list[dict[str, Any]] = []
        self.event_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.state = ExecutionState.RUNNING
        self.step_index = 0
        self.pending_approval: Approval | None = None
        self.approval_status = "NOT_REQUIRED"
        # The MCP runbook tool stays open while a human approves. Signalling this
        # event resumes that same execution and, in turn, the same TrueFoundry turn.
        self.approval_event = asyncio.Event()
        self.progress_event = asyncio.Event()
        self.runner_task: asyncio.Task[dict[str, Any]] | None = None
        self._emit("RUN_STARTED", input=dict(inputs or {}))
        if self.context.get("selection_reason"):
            self._emit(
                "RUNBOOK_SELECTED",
                selection_reason=self.context["selection_reason"],
                selected_runbook=self.runbook_id,
            )

    def _is_destructive(self, step: RunbookStep) -> bool:
        # An unknown tool cannot become automatic through a YAML typo or a
        # mistaken destructive: false declaration.
        return step.destructive or step.tool not in self.READ_ONLY_TOOLS

    def _emit(self, event_type: str, **details: Any) -> None:
        event = {
            "event": event_type,
            "sequence": len(self.events) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.execution_id,
            "runbook_id": self.runbook_id,
            **details,
        }
        self.events.append(event)
        self.event_sink.write(event)
        for subscriber in self.event_subscribers:
            subscriber.put_nowait(event)

    def subscribe_events(self) -> asyncio.Queue[dict[str, Any]]:
        subscriber: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.event_subscribers.add(subscriber)
        return subscriber

    def unsubscribe_events(self, subscriber: asyncio.Queue[dict[str, Any]]) -> None:
        self.event_subscribers.discard(subscriber)

    def _record_context(self, step: RunbookStep, arguments: dict[str, Any], result: Any) -> None:
        self.context[step.id] = result
        self.execution_context["completed_steps"].append(step.id)
        self.execution_context["step_results"][step.id] = result
        discovered = self.execution_context["discovered_variables"]
        if step.id == "get_flight" and isinstance(result, dict):
            discovered.update(
                {key: result[key] for key in ("flight_id", "origin", "destination", "delay_minutes") if key in result}
            )
        elif step.id == "get_roster" and isinstance(result, list):
            discovered["crew_ids"] = [item.get("crew_id") for item in result if isinstance(item, dict)]
            discovered["affected_crew"] = result
        elif step.id == "identify_constraint" and isinstance(result, dict):
            findings = result.get("constraints", [])
            self.execution_context["findings"] = findings if isinstance(findings, list) else []
            discovered["constraints"] = self.execution_context["findings"]
        elif step.id == "search_reserve" and isinstance(result, dict):
            candidates = result.get("candidates", [])
            if candidates:
                discovered["candidate"] = candidates[0]
        elif step.id == "validate_candidate" and isinstance(result, dict):
            discovered["candidate"] = result
        self._emit("STEP_COMPLETED", step_id=step.id, tool=step.tool, arguments=arguments, result=result)
        observation, _ = observe_and_decide(step.id, result)
        if observation:
            self._emit("OBSERVATION", step_id=step.id, message=observation, checks=check_details(step.id, result))
        if step.id == "identify_constraint" and self.execution_context["findings"]:
            for finding in self.execution_context["findings"]:
                self._emit("FINDING_CREATED", step_id=step.id, finding=finding)
        if step.id == "simulate_change":
            self._emit("SIMULATION_COMPLETED", step_id=step.id, result=result)
        if step.id == "apply_change":
            self._emit("ACTION_EXECUTED", step_id=step.id, tool=step.tool, arguments=arguments, result=result)
        if step.id == "verify":
            self._emit("VERIFICATION_COMPLETED", step_id=step.id, result=result)

    def _block(
        self,
        step: RunbookStep,
        reason: str,
        result: Any = None,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.state = ExecutionState.BLOCKED
        self.failure = {"step_id": step.id, "tool": step.tool, "reason": reason}
        if result is not None:
            self.context[step.id] = result
            self.execution_context["step_results"][step.id] = result
            self.step_results.append({
                "step_id": step.id,
                "tool": step.tool,
                "arguments": arguments or {},
                "status": "BLOCKED",
                "result": result,
                "reason": reason,
            })
            observation, _ = observe_and_decide(step.id, result)
            if observation:
                self._emit("OBSERVATION", step_id=step.id, message=observation, checks=check_details(step.id, result))
        self._emit("STEP_FAILED", **self.failure, result=result)
        self._emit("RUN_BLOCKED", **self.failure)
        print(f"RUNBOOK BLOCKED: {step.id} — {reason}", flush=True)
        self.progress_event.set()
        return self.to_dict()

    async def execute_step(self, step: RunbookStep) -> dict[str, Any] | None:
        """Execute one step, or stop before its tool call pending approval."""
        destructive = self._is_destructive(step)
        self._emit(
            "REASONING_SUMMARY",
            step_id=step.id,
            message=plan_for_step(step, self.context, approved=self.state == ExecutionState.APPROVED),
        )
        if destructive and self.state != ExecutionState.APPROVED:
            self.state = ExecutionState.WAITING_FOR_APPROVAL
            self.pending_approval = Approval.create(
                self.execution_id,
                self.runbook_id,
                step.id,
                step.tool,
                resolve_value(step.arguments, self.context),
            )
            self.approval_status = ExecutionState.WAITING_FOR_APPROVAL.value
            self.execution_context["pending_action"] = self._pending_action()
            proposal = self._approval_proposal()
            self._emit(
                "APPROVAL_REQUESTED",
                step_id=step.id,
                tool=step.tool,
                arguments=self.pending_approval.arguments,
                action_hash=self.pending_approval.action_hash,
                proposal=proposal,
            )
            self.progress_event.set()
            print("🛑 Approval required", flush=True)
            print(f"Action: {step.tool}", flush=True)
            print("Execution has been blocked.", flush=True)
            print("PROPOSED CHANGE", flush=True)
            print(f"Flight: {proposal.get('flight_id')}", flush=True)
            print(
                f"REMOVE: {proposal.get('remove_crew_id')}  →  "
                f"ADD: {proposal.get('replacement_crew_id')}"
                + (
                    f" ({proposal['candidate_name']})"
                    if proposal.get("candidate_name") else ""
                ),
                flush=True,
            )
            candidate_valid = proposal.get("candidate_validation", {}).get("valid")
            if candidate_valid is not None:
                print(f"Candidate validation: {'PASS' if candidate_valid else 'FAIL'}", flush=True)
            simulation = proposal.get("simulation", {})
            if simulation.get("safe") is not None:
                print(f"Simulation: {'PASS' if simulation['safe'] else 'FAIL'}", flush=True)
            for check, passed in proposal.get("simulation_checks", {}).items():
                print(f"{'✓' if passed else '✗'} {check.replace('_', ' ')}", flush=True)
            if simulation.get("issues"):
                print("Simulation issues: " + "; ".join(map(str, simulation["issues"])), flush=True)
            if proposal.get("production_state_modified") is False:
                print("No production state has been modified.", flush=True)
            print("Approve or reject this exact action to continue.", flush=True)
            print(
                "APPROVAL REQUEST: "
                + json.dumps(
                    {
                        "run_id": self.execution_id,
                        "runbook_id": self.runbook_id,
                        "current_step": step.id,
                        "completed_steps": [
                            result["step_id"] for result in self.step_results
                        ],
                        "approval_status": self.approval_status,
                        "pending_action": self._pending_action(),
                        "approval_id": self.pending_approval.approval_id,
                        "action_hash": self.pending_approval.action_hash,
                        "proposal": proposal,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return None

        if destructive:
            # Approval is valid only for this exact runbook step and the exact
            # resolved arguments captured when the gate was reached.
            if (
                self.pending_approval is None
                or self.pending_approval.step_id != step.id
                or self.pending_approval.tool != step.tool
            ):
                raise RuntimeError("Approval does not match the pending action")
            arguments = self.pending_approval.arguments
        else:
            arguments = resolve_value(step.arguments, self.context)
        self._emit("STEP_STARTED", step_id=step.id, tool=step.tool, arguments=arguments)
        self._emit("TOOL_CALLED", step_id=step.id, tool=step.tool, arguments=arguments)
        print(f"RUNBOOK STEP: {step.id} -> {step.tool}", flush=True)
        result = await self.tool_executor.call(step.tool, arguments, step.timeout)
        self._emit("TOOL_RESULT", step_id=step.id, tool=step.tool, result=result)
        print(f"✓ {step.id}", flush=True)
        return result

    async def run(self) -> dict[str, Any]:
        if self.state not in (ExecutionState.RUNNING, ExecutionState.APPROVED):
            raise RuntimeError(f"Cannot run execution in state {self.state.value}")

        while self.step_index < len(self.runbook.steps):
            step = self.runbook.steps[self.step_index]
            if step.when and not condition_is_true(step.when, self.context):
                self.step_results.append(
                    {
                        "step_id": step.id,
                        "tool": step.tool,
                        "status": "SKIPPED",
                        "reason": f"Runbook condition was false: {step.when}",
                    }
                )
                self.context[step.id] = None
                self._emit("STEP_SKIPPED", step_id=step.id, tool=step.tool, reason=f"Runbook condition was false: {step.when}")
                print(f"↷ {step.id}: condition false", flush=True)
                self.step_index += 1
                continue
            try:
                result = await self.execute_step(step)
            except Exception as exc:
                self.state = ExecutionState.FAILED
                if isinstance(exc, ToolTimeoutError):
                    reason = f"CrewOps tool timed out: {exc}"
                elif isinstance(exc, (ToolUnavailableError, ConnectionError)):
                    reason = f"CrewOps service unavailable: {exc}"
                else:
                    reason = f"Tool execution failed: {exc}"
                self.failure = {"step_id": step.id, "tool": step.tool, "reason": reason}
                self.step_results.append(
                    {"step_id": step.id, "tool": step.tool, "status": "FAILED", "error": str(exc)}
                )
                self._emit("STEP_FAILED", **self.failure)
                self._emit("RUN_FAILED", **self.failure)
                self.pending_approval = None
                self.execution_context.pending_action = None
                print(f"RUNBOOK PAUSED: {step.id} — {reason}", flush=True)
                self.progress_event.set()
                return self.to_dict()

            if result is None and self.state == ExecutionState.WAITING_FOR_APPROVAL:
                return self.to_dict()

            if self._is_destructive(step):
                if self.pending_approval is None:
                    raise RuntimeError("Approved action arguments are missing")
                arguments = self.pending_approval.arguments
            else:
                arguments = resolve_value(step.arguments, self.context)
            block_reason = None
            if step.id == "identify_constraint" and (
                not isinstance(result, dict) or result.get("replacement_supported") is not True
            ):
                block_reason = "Duty investigation did not identify exactly one supported crew constraint."
            elif step.id == "search_reserve" and (
                not isinstance(result, dict) or not result.get("candidates")
            ):
                block_reason = "No reserve candidate was returned by CrewOps."
            elif step.id == "validate_candidate" and (
                not isinstance(result, dict) or result.get("valid") is not True
            ):
                block_reason = "Candidate validation failed: " + issues_text(result)
            elif step.id == "simulate_change" and (
                not isinstance(result, dict) or result.get("safe") is not True
            ):
                block_reason = "Read-only roster simulation failed: " + issues_text(result)
            elif step.id == "verify" and (
                not isinstance(result, dict) or result.get("verified") is not True
            ):
                block_reason = "Final roster verification did not pass."
            if block_reason:
                return self._block(step, block_reason, result=result, arguments=arguments)
            self._record_context(step, arguments, result)
            step_result = {
                "step_id": step.id,
                "tool": step.tool,
                "arguments": arguments,
                "status": "COMPLETED",
                "result": result,
            }
            if self.state == ExecutionState.APPROVED:
                step_result["approval"] = ExecutionState.APPROVED.value
            self.step_results.append(step_result)
            self.step_index += 1
            if self.state == ExecutionState.APPROVED:
                self.pending_approval = None
                self.execution_context["pending_action"] = None
                self.state = ExecutionState.RUNNING

        self.state = ExecutionState.COMPLETED
        self._emit("RUN_COMPLETED", steps_completed=len(self.execution_context["completed_steps"]))
        self.progress_event.set()
        return self.to_dict()

    def submit_decision(
        self,
        decision: str,
        approval_id: str,
        run_id: str,
        runbook_id: str,
        action: dict[str, Any],
    ) -> None:
        """Validate a human decision against the exact pending action and signal it."""
        pending = self.pending_approval
        if self.state != ExecutionState.WAITING_FOR_APPROVAL or pending is None:
            raise ValueError("There is no destructive step waiting for approval")
        if run_id != self.execution_id:
            raise ValueError("run_id does not match the pending execution")
        if runbook_id != self.runbook_id:
            raise ValueError("runbook_id does not match the pending run")
        if not pending.matches_id(approval_id):
            raise ValueError("Approval ID does not match the pending action")
        if pending.is_expired():
            raise ValueError("Approval has expired")
        if not isinstance(action, dict):
            raise ValueError("action must contain the pending step, tool, and arguments")
        if not pending.matches_action(action):
            raise ValueError("Action does not match the exact pending step and arguments")
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be 'approve' or 'reject'")
        self.progress_event.clear()
        if decision == "approve":
            self.state = ExecutionState.APPROVED
            self.approval_status = ExecutionState.APPROVED.value
            self._emit("APPROVAL_RECEIVED", decision="approve", step_id=pending.step_id, tool=pending.tool, arguments=pending.arguments, action_hash=pending.action_hash)
        elif decision == "reject":
            self._emit("APPROVAL_RECEIVED", decision="reject", step_id=pending.step_id, tool=pending.tool, arguments=pending.arguments, action_hash=pending.action_hash)
            self.step_results.append(
                {
                    "step_id": pending.step_id,
                    "tool": pending.tool,
                    "status": ExecutionState.REJECTED.value,
                }
            )
            self.state = ExecutionState.REJECTED
            self.approval_status = ExecutionState.REJECTED.value
            self._emit("RUN_REJECTED", step_id=pending.step_id, tool=pending.tool)
            self.pending_approval = None
            self.execution_context["pending_action"] = None
            self.progress_event.set()
        self.approval_event.set()

    def _pending_action(self) -> dict[str, Any]:
        if self.pending_approval is None:
            raise RuntimeError("There is no pending action")
        return self.pending_approval.action

    def to_dict(self) -> dict[str, Any]:
        if self.state == ExecutionState.COMPLETED:
            return self._completed_summary()

        current_step = (
            self.runbook.steps[self.step_index].id
            if self.step_index < len(self.runbook.steps)
            else None
        )
        if self.state in {ExecutionState.FAILED, ExecutionState.BLOCKED}:
            current_step = getattr(self, "failure", {}).get("step_id", current_step)
        payload: dict[str, Any] = {
            "run_id": self.execution_id,
            "runbook_id": self.runbook_id,
            "execution_id": self.execution_id,
            "runbook": self.runbook.name,
            "current_step": current_step,
            "completed_steps": [
                result["step_id"]
                for result in self.step_results
                if result.get("status") == "COMPLETED"
            ],
            "approval_status": self.approval_status,
            "state": self.state.value,
            "status": self.state.value,
            "steps": self.step_results,
            "execution_context": self.execution_context.to_dict(),
            "events": self.events,
            "event_log": str(self.event_log_path),
        }
        if self.state in {ExecutionState.FAILED, ExecutionState.BLOCKED}:
            payload["status"] = "paused" if self.state == ExecutionState.FAILED else "blocked"
            payload["failure"] = getattr(self, "failure", None)
            destructive_step_ids = {
                step.id for step in self.runbook.steps if self._is_destructive(step)
            }
            payload["no_destructive_action_attempted"] = not any(
                event.get("event") == "TOOL_CALLED"
                and (
                    event.get("tool") in self.DESTRUCTIVE_TOOLS
                    or event.get("step_id") in destructive_step_ids
                )
                for event in self.events
            )
        if self.pending_approval is not None and self.state == ExecutionState.WAITING_FOR_APPROVAL:
            payload["approval_required"] = {
                **self._pending_action(),
                "approval_id": self.pending_approval.approval_id,
                "action_hash": self.pending_approval.action_hash,
                "expires_at": self.pending_approval.expires_at.isoformat(),
                "message": "Execution has been blocked.",
                "approval_endpoint": f"/runbook-approvals/{self.execution_id}",
                "proposal": self._approval_proposal(),
            }
            payload["pending_action"] = self._pending_action()
            payload["events"] = self.events
        return payload

    def _approval_proposal(self) -> dict[str, Any]:
        simulation = self.context.get("simulate_change") or {}
        candidate = self.context.get("validate_candidate") or {}
        flight = self.context.get("get_flight") or {}
        constraints = (self.context.get("identify_constraint") or {}).get("constraints", [])
        constraint = constraints[0] if constraints else {}
        prior_actions = [event for event in self.events if event.get("event") == "ACTION_EXECUTED"]
        prior_mutation_values = [
            event.get("result", {}).get("mutated")
            for event in prior_actions
            if isinstance(event.get("result"), dict)
        ]
        production_state_modified = (
            any(value is True for value in prior_mutation_values)
            if len(prior_mutation_values) == len(prior_actions)
            and all(value is not None for value in prior_mutation_values)
            else False if not prior_actions else None
        )
        return {
            "flight_id": flight.get("flight_id", self.context.get("flight_id")),
            "delay_minutes": flight.get("delay_minutes"),
            "remove_crew_id": constraint.get("crew_id"),
            "replacement_crew_id": candidate.get("crew_id"),
            "candidate_name": candidate.get("name"),
            "candidate_validation": candidate,
            "simulation": simulation,
            "simulation_checks": simulation.get("checks", {}),
            "mock_action": self.runbook.steps[self.step_index].mock,
            "production_state_modified": production_state_modified,
            "message": "Review the proposed change and read-only simulation before approving. No production state has been modified.",
        }

    def _completed_summary(self) -> dict[str, Any]:
        """Return the decision-relevant run result without every tool payload."""
        flight = self.context.get("get_flight") or {}
        constraints = (self.context.get("identify_constraint") or {}).get(
            "constraints", []
        )
        constraint = constraints[0] if constraints else None
        candidates = (self.context.get("search_reserve") or {}).get(
            "candidates", []
        )
        candidate = self.context.get("validate_candidate") or (
            candidates[0] if candidates else {}
        )
        simulation = self.context.get("simulate_change") or {}
        apply_result = self.context.get("apply_change") or {}
        verification_result = self.context.get("verify") or {}
        original_crew_ids = {
            member.get("crew_id")
            for member in self.context.get("get_roster", [])
            if isinstance(member, dict)
        }
        actual_crew_ids = set(verification_result.get("actual_crew_ids", []))
        applied_step = next(
            (
                result
                for result in self.step_results
                if result.get("step_id") == "apply_change"
                and result.get("status") == "COMPLETED"
            ),
            None,
        )
        completed_steps = [
            result["step_id"]
            for result in self.step_results
            if result.get("status") == "COMPLETED"
        ]
        skipped_steps = [
            result["step_id"]
            for result in self.step_results
            if result.get("status") == "SKIPPED"
        ]
        validation = candidate.get("checks") or {
            "availability": candidate.get("reserve_available"),
            "qualification": (
                candidate.get("rank") == constraint.get("required_rank")
                if candidate.get("rank") is not None and constraint else None
            ),
            "duty_limit": candidate.get("duty_limit_passed"),
            "certification": candidate.get("certification_valid"),
        }
        validation.update(simulation.get("checks", {}))
        validation["roster_simulation_safe"] = simulation.get("safe")
        where = {
            "flight_id": flight.get("flight_id", self.context.get("flight_id")),
            "affected_crew": [
                {"crew_id": item.get("crew_id"), "name": item.get("name"), "rank": item.get("rank")}
                for item in self.context.get("get_roster", []) if isinstance(item, dict)
            ],
            "constrained_crew_id": constraint.get("crew_id"),
        }
        why = {
            "delay_minutes": flight.get("delay_minutes"),
            "duty_constraints": constraints,
            "rule": (self.context.get("identify_constraint") or {}).get("rule"),
        }
        impact = None
        if constraint:
            projected = constraint.get("projected_duty_minutes")
            limit = constraint.get("max_allowed_minutes")
            overage = constraint.get("over_limit_minutes")
            if all(isinstance(value, (int, float)) for value in (projected, limit, overage)):
                impact = (
                    f"Projected duty is {projected} minutes, above the recorded maximum "
                    f"of {limit} minutes by {overage} minutes."
                )
            else:
                impact = constraint.get("reason")
        elif self.context.get("identify_constraint"):
            impact = "The duty investigation reported no crew member over the recorded limit."
        proposed = {
            "remove_crew_id": simulation.get("proposed_removal", constraint.get("crew_id")),
            "replacement_crew_id": simulation.get("proposed_replacement", candidate.get("crew_id")),
            "candidate_name": candidate.get("name"),
        }
        action = (
            {
                "step_id": applied_step["step_id"],
                "tool": applied_step["tool"],
                "arguments": applied_step["arguments"],
                "approval": applied_step.get("approval"),
                "mock": apply_result.get("mock"),
                "mutated": apply_result.get("mutated"),
            }
            if applied_step else None
        )
        verified = verification_result.get("verified") is True
        if action and verified and action.get("mutated"):
            status = "RESOLVED"
        elif action and verified and action.get("mock"):
            status = "VERIFIED_MOCK"
        else:
            status = "COMPLETED" if verified else "UNVERIFIED"
        report = {
            "title": "CREWOPS RUNBOOK RESULT",
            "incident": {
                "flight_id": flight.get("flight_id", self.context.get("flight_id")),
                "origin": flight.get("origin"),
                "destination": flight.get("destination"),
                "delay_minutes": flight.get("delay_minutes"),
            },
            "where": where,
            "why": why,
            "so_what": impact,
            "proposed_remediation": proposed,
            "validation": validation,
            "approval": {
                "status": self.approval_status,
                "step_id": action.get("step_id") if action else None,
            },
            "execution": action,
            "verification": {
                "verified": verification_result.get("verified"),
                "status": verification_result.get("status"),
                "roster_changed": (
                    actual_crew_ids != original_crew_ids
                    if verification_result.get("actual_crew_ids") is not None else None
                ),
                "mock": verification_result.get("mock"),
                "mutated": verification_result.get("mutated"),
            },
            "status": status,
        }

        return {
            "run_id": self.execution_id,
            "runbook_id": self.runbook_id,
            "status": "completed" if status in {"RESOLVED", "VERIFIED_MOCK"} else "unverified",
            "state": self.state.value,
            "approval_status": self.approval_status,
            "steps_completed": len(completed_steps),
            "steps_skipped": len(skipped_steps),
            "incident": {
                "flight_id": flight.get("flight_id", self.context.get("flight_id")),
                "origin": flight.get("origin"),
                "destination": flight.get("destination"),
                "delay_minutes": flight.get("delay_minutes"),
            },
            "finding": constraint,
            "impact": impact,
            "remediation": {
                "candidate_id": candidate.get("crew_id"),
                "candidate_name": candidate.get("name"),
                "valid": candidate.get("valid"),
                "issues": candidate.get("issues", []),
            },
            "validation": validation,
            "action": action,
            "verification": {
                "verified": verification_result.get("verified"),
                "status": verification_result.get("status"),
                "roster_changed": (
                    actual_crew_ids != original_crew_ids
                    if verification_result.get("actual_crew_ids") is not None
                    else None
                ),
                "mock": verification_result.get("mock"),
                "mutated": verification_result.get("mutated"),
            },
            "report": report,
            "execution_context": {
                "input": self.execution_context["input"],
                "completed_steps": self.execution_context["completed_steps"],
                "discovered_variables": self.execution_context["discovered_variables"],
                "findings": self.execution_context["findings"],
                "pending_action": None,
            },
            "event_count": len(self.events),
            "event_log": str(self.event_log_path),
        }
