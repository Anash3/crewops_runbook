"""Per-run state without any transport or persistence dependency."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    input: dict[str, Any]
    completed_steps: list[str] = field(default_factory=list)
    step_results: dict[str, Any] = field(default_factory=dict)
    discovered_variables: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    pending_action: dict[str, Any] | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "completed_steps": self.completed_steps,
            "step_results": self.step_results,
            "discovered_variables": self.discovered_variables,
            "findings": self.findings,
            "pending_action": self.pending_action,
        }
