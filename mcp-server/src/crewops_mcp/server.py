"""Expose CrewOps data tools and proxy runbook execution to the backend."""

import asyncio
import hmac
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from crewops_mcp.constraints import identify_constraint
from crewops_mcp.database import Database
from crewops_mcp.tools import CrewOpsDatabaseTools


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    mcp_host: str
    mcp_port: int
    mcp_api_key: str | None
    backend_api_url: str
    backend_api_key: str | None
    proxy_timeout_seconds: float


def load_settings(root: Path = ROOT) -> Settings:
    load_dotenv(root / ".env")
    return Settings(
        database_url=os.getenv("DATABASE_URL"),
        mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
        mcp_port=int(os.getenv("MCP_PORT", "8000")),
        mcp_api_key=os.getenv("MCP_API_KEY") or None,
        backend_api_url=os.getenv("BACKEND_API_URL", "http://127.0.0.1:8001").rstrip("/"),
        backend_api_key=os.getenv("BACKEND_API_KEY") or None,
        proxy_timeout_seconds=float(os.getenv("RUNBOOK_PROXY_TIMEOUT_SECONDS", "3600")),
    )


class MCPBearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, api_key: str | None) -> None:
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if self.api_key and request.url.path.startswith("/mcp"):
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {self.api_key}"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_server(
    settings: Settings | None = None,
    *,
    connect: Any = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[FastMCP, Any, Database]:
    settings = settings or load_settings()
    database = Database(settings.database_url)
    tools = CrewOpsDatabaseTools(connect or database.connect)
    mcp = FastMCP("CrewOps", host=settings.mcp_host, port=settings.mcp_port)

    for function in (
        tools.flight_get,
        tools.flight_roster,
        tools.duty_clock_get,
        identify_constraint,
        tools.reserve_search,
        tools.validate_candidate,
        tools.simulate_roster_change,
        tools.roster_apply_change,
        tools.verify_roster,
    ):
        mcp.tool()(function)

    @mcp.tool()
    def agent_note(message: str) -> dict[str, str]:
        """Record a short, public model-authored observation for the operator."""
        note = message.strip()
        if not note or len(note) > 600:
            raise ValueError("message must contain 1 to 600 characters")
        return {"message": note}

    @mcp.tool()
    async def runbook_execute(
        flight_id: str, ctx: Context, case_id: str | None = None
    ) -> dict[str, Any]:
        """Execute a human-authored runbook in the backend and return its result."""
        async def report_waiting() -> None:
            heartbeat = 0
            while True:
                await asyncio.sleep(15)
                heartbeat += 1
                try:
                    await ctx.report_progress(
                        float(heartbeat), None, "Runbook is executing or awaiting human approval"
                    )
                except Exception:
                    # Progress notifications never control the approval gate.
                    continue

        headers = (
            {"Authorization": f"Bearer {settings.backend_api_key}"}
            if settings.backend_api_key else None
        )
        progress_task = asyncio.create_task(report_waiting())
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(settings.proxy_timeout_seconds, connect=10),
                headers=headers,
            ) as client:
                response = await client.post(
                    f"{settings.backend_api_url}/runbook-executions",
                    json={"flight_id": flight_id, "case_id": case_id},
                )
                response.raise_for_status()
                return response.json()
        finally:
            progress_task.cancel()
            await asyncio.gather(progress_task, return_exceptions=True)

    app = mcp.streamable_http_app()
    app.add_middleware(MCPBearerAuthMiddleware, api_key=settings.mcp_api_key)
    return mcp, app, database


mcp, app, database = create_server()
