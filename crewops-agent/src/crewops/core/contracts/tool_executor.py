from typing import Any, Protocol


class ToolExecutor(Protocol):
    async def call(self, tool: str, arguments: dict[str, Any], timeout: float) -> Any: ...
