"""Tests for the standalone CrewOps FastMCP process."""

import asyncio
import socket
import unittest
from dataclasses import replace
from datetime import date
from typing import Any

import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from crewops_mcp.server import create_server, load_settings
from crewops_mcp.tools import CrewOpsDatabaseTools


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def mappings(self):
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_: Any):
        return None

    def execute(self, query: Any, params: dict[str, Any]):
        sql = str(query)
        if "FROM flight_roster fr" in sql:
            return FakeResult([{"crew_id": "C102", "name": "Alice", "rank": "Captain"},
                               {"crew_id": "C231", "name": "Bob", "rank": "First Officer"}])
        if "FROM duty_clock dc" in sql:
            return FakeResult([{"crew_id": "C102", "total_minutes": 600, "max_allowed": 720},
                               {"crew_id": "C231", "total_minutes": 300, "max_allowed": 720}])
        if "FROM reserve r" in sql:
            return FakeResult([{"crew_id": "C345", "name": "Carol", "rank": "Captain", "base": "JFK"}])
        if "FROM crew c" in sql:
            return FakeResult([{"crew_id": "C345", "name": "Carol", "rank": "Captain", "base": "JFK",
                               "flight_origin": "JFK", "reserve_available": True,
                               "total_minutes": 120, "max_allowed": 720, "expires_at": date.today()}])
        return FakeResult([{"flight_id": params["flight_id"], "origin": "JFK",
                            "destination": "LAX", "delay_minutes": 240}])


class CrewOpsToolTests(unittest.TestCase):
    def test_candidate_validation_and_simulation(self):
        tools = CrewOpsDatabaseTools(FakeConnection)
        candidate = tools.validate_candidate("FL-1042", "C345", "Captain", 240)
        simulation = tools.simulate_roster_change("FL-1042", "C102", "C345", "Captain", 240)
        self.assertTrue(candidate["valid"])
        self.assertTrue(all(candidate["checks"].values()))
        self.assertTrue(simulation["safe"])
        self.assertTrue(simulation["checks"]["replacement_not_already_assigned"])


class MCPProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_runbook_tool_proxies_exact_flight_id(self):
        received = []

        async def backend_execute(request: Request):
            received.append((await request.json(), request.headers.get("authorization")))
            return JSONResponse({"run_id": "run-123", "state": "COMPLETED", "steps_completed": 9})

        backend = Starlette(routes=[Route("/runbook-executions", backend_execute, methods=["POST"])])
        listener = socket.socket()
        try:
            listener.bind(("127.0.0.1", 0))
        except PermissionError:
            listener.close()
            self.skipTest("local listener unavailable")
        listener.listen(128)
        listener.setblocking(False)
        port = listener.getsockname()[1]
        settings = replace(load_settings(), mcp_port=port, backend_api_key="test-key")
        _, app, _ = create_server(settings, connect=FakeConnection,
                                  transport=httpx.ASGITransport(app=backend, client=("127.0.0.1", 12345)))
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            for _ in range(200):
                if server.started:
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(server.started)
            async with httpx.AsyncClient() as http_client:
                async with streamable_http_client(
                    f"http://127.0.0.1:{port}/mcp", http_client=http_client
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool("runbook_execute", {"flight_id": "FL-1042"})
            self.assertFalse(result.isError)
            self.assertEqual(result.structuredContent["run_id"], "run-123")
            self.assertEqual(received, [({"flight_id": "FL-1042"}, "Bearer test-key")])
        finally:
            server.should_exit = True
            await asyncio.wait_for(server_task, 5)
            listener.close()
