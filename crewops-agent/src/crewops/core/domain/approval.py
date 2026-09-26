"""An immutable approval target for one exact runbook action."""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Approval:
    run_id: str
    runbook_id: str
    step_id: str
    tool: str
    arguments_json: str
    approval_id: str
    expires_at: datetime

    @classmethod
    def create(
        cls,
        run_id: str,
        runbook_id: str,
        step_id: str,
        tool: str,
        arguments: dict[str, Any],
    ) -> "Approval":
        return cls(
            run_id=run_id,
            runbook_id=runbook_id,
            step_id=step_id,
            tool=tool,
            arguments_json=canonical_json(arguments),
            approval_id=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

    @property
    def arguments(self) -> dict[str, Any]:
        return json.loads(self.arguments_json)

    @property
    def action(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "tool": self.tool, "arguments": self.arguments}

    @property
    def action_hash(self) -> str:
        payload = [self.run_id, self.runbook_id, self.action]
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def matches_action(self, action: dict[str, Any]) -> bool:
        try:
            return canonical_json(action) == canonical_json(self.action)
        except (TypeError, ValueError):
            return False

    def matches_id(self, approval_id: str) -> bool:
        return isinstance(approval_id, str) and secrets.compare_digest(
            approval_id, self.approval_id
        )

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at
