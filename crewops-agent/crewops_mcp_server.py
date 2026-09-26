"""Streamable HTTP MCP server exposing CrewOps tools and the runbook executor."""

import os
import hmac
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()

from db import get_connection
from runbook_executor import decide_approval, execute_runbook

mcp = FastMCP(
    "CrewOps",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
)


@mcp.tool()
def flight_get(flight_id: str) -> dict[str, Any]:
    """Get the scheduled details and current status of a flight by flight ID."""
    query = text(
        """SELECT flight_id, origin, destination, scheduled_time, status,
                  delay_minutes
           FROM flight
           WHERE flight_id = :flight_id"""
    )
    with get_connection() as conn:
        row = conn.execute(query, {"flight_id": flight_id}).mappings().fetchone()
    if row is None:
        raise ValueError(f"Flight {flight_id} was not found")
    return dict(row)


@mcp.tool()
def flight_roster(flight_id: str) -> list[dict[str, Any]]:
    """List the crew assigned to a flight."""
    query = text(
        """SELECT c.crew_id, c.name, c.rank
           FROM flight_roster fr
           JOIN flight f ON fr.flight_id = f.id
           JOIN crew c ON fr.crew_id = c.id
           WHERE f.flight_id = :flight_id
           ORDER BY c.crew_id"""
    )
    with get_connection() as conn:
        rows = conn.execute(query, {"flight_id": flight_id}).mappings().fetchall()
    return [dict(row) for row in rows]


@mcp.tool()
def duty_clock_get(crew_id: str) -> dict[str, Any]:
    """Get duty clock totals and limits for a crew member."""
    query = text(
        """SELECT c.crew_id, dc.total_minutes, dc.max_allowed
           FROM duty_clock dc
           JOIN crew c ON dc.crew_id = c.id
           WHERE c.crew_id = :crew_id"""
    )
    with get_connection() as conn:
        row = conn.execute(query, {"crew_id": crew_id}).mappings().fetchone()
    if row is None:
        raise ValueError(f"Duty clock for crew member {crew_id} was not found")
    return dict(row)


@mcp.tool()
async def runbook_execute(flight_id: str) -> dict[str, Any]:
    """Execute the human-authored delayed-flight runbook through its safe steps."""
    return await execute_runbook(
        runbook_path=Path(__file__).with_name("runbooks") / "crew_delay_resolution.yaml",
        mcp_url=os.getenv("CREWOPS_MCP_URL", "http://127.0.0.1:8000/mcp"),
        flight_id=flight_id,
        mcp_api_key=os.getenv("MCP_API_KEY"),
    )


app = mcp.streamable_http_app()


class MCPBearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        expected = os.getenv("MCP_API_KEY")
        if expected and request.url.path.startswith("/mcp"):
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {expected}"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


app.add_middleware(MCPBearerAuthMiddleware)


async def runbook_approval(request: Request) -> JSONResponse:
    """Receive a human decision outside the MCP tools available to the agent."""
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return JSONResponse({"detail": "Approval is restricted to localhost"}, status_code=403)

    expected = os.getenv("RUNBOOK_APPROVAL_API_KEY")
    if expected:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {expected}"):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(
                {"detail": "Approval body must be an object"}, status_code=400
            )
        result = await decide_approval(
            request.path_params["execution_id"], body.get("decision", "")
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    print(
        f"HUMAN APPROVAL: {body['decision']} execution "
        f"{request.path_params['execution_id']}",
        flush=True,
    )
    return JSONResponse(result)


app.add_route(
    "/runbook-approvals/{execution_id}", runbook_approval, methods=["POST"]
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
    )
