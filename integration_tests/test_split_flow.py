"""Exercise the backend and FastMCP as two independent HTTP processes."""

import asyncio
import socket
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from crewops.api.server import create_api
from crewops.core.enums.execution_status import ExecutionState
from crewops.infrastructure.bootstrap import create_application
from crewops.infrastructure.config.settings import load_settings as backend_settings
from crewops.infrastructure.mcp.client import MCPClient
from crewops_mcp.server import create_server, load_settings as mcp_settings


class Result:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def mappings(self):
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_: Any):
        return None

    def execute(self, query: Any, params: dict[str, Any]):
        sql = str(query)
        if "FROM flight_roster fr" in sql:
            return Result([{"crew_id": "C102", "name": "Alice", "rank": "Captain"},
                           {"crew_id": "C231", "name": "Bob", "rank": "First Officer"}])
        if "FROM duty_clock dc" in sql:
            return Result([{"crew_id": "C102", "total_minutes": 600, "max_allowed": 720},
                           {"crew_id": "C231", "total_minutes": 300, "max_allowed": 720}])
        if "FROM reserve r" in sql:
            return Result([{"crew_id": "C345", "name": "Carol", "rank": "Captain", "base": "JFK"}])
        if "FROM crew c" in sql:
            return Result([{"crew_id": "C345", "name": "Carol", "rank": "Captain", "base": "JFK",
                           "flight_origin": "JFK", "reserve_available": True, "total_minutes": 120,
                           "max_allowed": 720, "expires_at": date.today()}])
        return Result([{"flight_id": params["flight_id"], "origin": "JFK",
                       "destination": "LAX", "delay_minutes": 240}])


def listener() -> socket.socket:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    sock.setblocking(False)
    return sock


class SplitFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_backend_mcp_approval_and_verification(self):
        try:
            backend_socket, mcp_socket = listener(), listener()
        except PermissionError:
            self.skipTest("local listeners unavailable")
        backend_port = backend_socket.getsockname()[1]
        mcp_port = mcp_socket.getsockname()[1]
        with tempfile.TemporaryDirectory() as temp:
            settings = replace(
                backend_settings(), backend_port=backend_port,
                crewops_mcp_url=f"http://127.0.0.1:{mcp_port}/mcp",
                mcp_api_key=None, backend_api_key=None, approval_api_key=None,
                event_log_path=Path(temp) / "events.jsonl",
            )
            application = create_application(settings)
            backend_app, _ = create_api(application)
            fastmcp_settings = replace(
                mcp_settings(), mcp_port=mcp_port, mcp_api_key=None, backend_api_key=None,
                backend_api_url=f"http://127.0.0.1:{backend_port}",
            )
            _, mcp_app, _ = create_server(fastmcp_settings, connect=Connection)
            backend_server = uvicorn.Server(uvicorn.Config(backend_app, log_level="error", lifespan="on"))
            mcp_server = uvicorn.Server(uvicorn.Config(mcp_app, log_level="error", lifespan="on"))
            backend_task = asyncio.create_task(backend_server.serve(sockets=[backend_socket]))
            mcp_task = asyncio.create_task(mcp_server.serve(sockets=[mcp_socket]))
            call_task = None
            try:
                for _ in range(200):
                    if backend_server.started and mcp_server.started:
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(backend_server.started and mcp_server.started)
                call_task = asyncio.create_task(MCPClient(settings.crewops_mcp_url).call(
                    "runbook_execute", {"flight_id": "FL-1042"}, 60
                ))
                for _ in range(500):
                    pending = application.executions.all()
                    if pending and pending[0].state == ExecutionState.WAITING_FOR_APPROVAL:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("split run did not reach approval")
                run = pending[0]
                request = run.to_dict()
                self.assertFalse(call_task.done())
                # Keep the MCP response stream idle beyond HTTPX's default
                # read timeout and the proxy's first progress heartbeat.
                await asyncio.sleep(17)
                self.assertFalse(call_task.done())
                async with httpx.AsyncClient() as client:
                    approved = await client.post(
                        f"http://127.0.0.1:{backend_port}/runbook-approvals/{run.execution_id}",
                        json={"decision": "approve", "approval_id": request["approval_required"]["approval_id"],
                              "run_id": run.execution_id, "runbook_id": run.runbook_id,
                              "action": request["pending_action"]},
                    )
                self.assertEqual(approved.status_code, 200, approved.text)
                result = await call_task
                self.assertEqual(result["run_id"], run.execution_id)
                self.assertEqual(result["steps_completed"], 9)
                self.assertEqual(result["report"]["status"], "VERIFIED_MOCK")
                self.assertFalse(result["verification"]["roster_changed"])
            finally:
                if call_task and not call_task.done():
                    call_task.cancel()
                    await asyncio.gather(call_task, return_exceptions=True)
                backend_server.should_exit = True
                mcp_server.should_exit = True
                await asyncio.gather(backend_task, mcp_task)
                backend_socket.close()
                mcp_socket.close()
