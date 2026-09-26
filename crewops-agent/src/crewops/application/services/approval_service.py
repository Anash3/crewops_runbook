"""Apply a human decision to the execution already awaiting it."""

import hmac
from typing import Any

from crewops.core.contracts.repositories import ExecutionRepository
from crewops.orchestration.executor import RunbookExecution


class ApprovalService:
    def __init__(self, repository: ExecutionRepository[RunbookExecution]) -> None:
        self.repository = repository

    async def decide(
        self,
        execution_id: str,
        decision: str,
        approval_id: str,
        run_id: str,
        runbook_id: str,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        execution = self.repository.get(execution_id)
        if execution is None:
            raise ValueError(f"No pending runbook execution {execution_id}")
        execution.submit_decision(decision, approval_id, run_id, runbook_id, action)
        await execution.progress_event.wait()
        return execution.to_dict()

    async def decide_by_id(
        self,
        approval_id: str,
        decision: str,
        run_id: str,
        action_hash: str,
    ) -> dict[str, Any]:
        """Apply a UI decision using only the engine's stored pending action."""
        execution = self.repository.get(run_id)
        pending = execution.pending_approval if execution else None
        if pending is None or not pending.matches_id(approval_id):
            raise ValueError("Approval was not found for this run")
        if not isinstance(action_hash, str) or not hmac.compare_digest(
            action_hash, pending.action_hash
        ):
            raise ValueError("Action hash does not match the pending action")
        if pending.is_expired():
            raise ValueError("Approval has expired")
        return await self.decide(
            run_id,
            decision,
            approval_id,
            pending.run_id,
            pending.runbook_id,
            pending.action,
        )
