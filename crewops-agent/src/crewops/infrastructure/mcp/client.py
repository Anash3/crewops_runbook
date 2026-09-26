"""CrewOps tool execution over MCP Streamable HTTP."""

import asyncio
import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from crewops.core.exceptions import ToolTimeoutError, ToolUnavailableError


class MCPClient:
    def __init__(self, url: str, api_key: str | None = None) -> None:
        self.url = url
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    async def call(self, tool: str, arguments: dict[str, Any], timeout: float) -> Any:
        async def invoke() -> Any:
            # A runbook_execute response can wait through human approval. The
            # default httpx read timeout is too short for that MCP SSE stream.
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(timeout, connect=10),
            ) as http_client:
                async with streamable_http_client(
                    self.url, http_client=http_client
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(tool, arguments)
                        if result.isError:
                            message = "; ".join(
                                getattr(item, "text", "") for item in result.content
                            )
                            raise RuntimeError(message or f"MCP tool {tool} failed")
                        if result.structuredContent is not None:
                            structured = result.structuredContent
                            if isinstance(structured, dict) and set(structured) == {"result"}:
                                return structured["result"]
                            return structured
                        texts = [
                            item.text
                            for item in result.content
                            if getattr(item, "type", None) == "text"
                        ]
                        if len(texts) == 1:
                            try:
                                return json.loads(texts[0])
                            except json.JSONDecodeError:
                                return texts[0]
                        return texts

        try:
            return await asyncio.wait_for(invoke(), timeout=timeout)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise ToolTimeoutError(f"MCP tool {tool} exceeded {timeout:g}s") from exc
        except (httpx.RequestError, ConnectionError, OSError) as exc:
            raise ToolUnavailableError(str(exc)) from exc
