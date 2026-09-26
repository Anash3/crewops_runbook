"""Application-scoped storage for active executions."""

from typing import Generic, TypeVar


T = TypeVar("T")


class InMemoryExecutionRepository(Generic[T]):
    def __init__(self) -> None:
        self._executions: dict[str, T] = {}

    def save(self, execution: T) -> None:
        self._executions[execution.execution_id] = execution  # type: ignore[attr-defined]

    def get(self, run_id: str) -> T | None:
        return self._executions.get(run_id)

    def delete(self, run_id: str) -> None:
        self._executions.pop(run_id, None)

    def all(self) -> list[T]:
        return list(self._executions.values())
