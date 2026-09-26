from typing import Any, Protocol


class EventSink(Protocol):
    path: str

    def write(self, event: dict[str, Any]) -> None: ...
