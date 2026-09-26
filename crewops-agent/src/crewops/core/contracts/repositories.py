from typing import Generic, Protocol, TypeVar


T = TypeVar("T")


class ExecutionRepository(Protocol, Generic[T]):
    def save(self, execution: T) -> None: ...

    def get(self, run_id: str) -> T | None: ...

    def delete(self, run_id: str) -> None: ...
