"""Exercise the application boundary and its MCP adapter."""

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
from crewops.api.server import create_api
from crewops.core.enums.execution_status import ExecutionState
from crewops.infrastructure.bootstrap import create_application
from crewops.infrastructure.config.settings import load_settings


class RecordingTools:
    def __init__(self, fail: str | None = None, invalid: bool = False, unsafe: bool = False):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail, self.invalid, self.unsafe = fail, invalid, unsafe

    async def call(self, tool: str, arguments: dict[str, Any], timeout: float) -> Any:
        self.calls.append((tool, arguments))
        if tool == self.fail:
            raise ConnectionError("CrewOps service unavailable")
        if tool == "flight_get":
            return {"flight_id": arguments["flight_id"], "origin": "JFK", "delay_minutes": 240}
        if tool == "flight_roster":
            return [{"crew_id": "C102", "rank": "Captain"}, {"crew_id": "C231", "rank": "First Officer"}]
        if tool == "duty_clock_get":
            return [{"crew_id": "C102", "total_minutes": 600, "max_allowed": 720}]
        if tool == "identify_constraint":
            return {"has_constraint": True, "replacement_supported": True,
                    "rule": "projected duty exceeds limit",
                    "constraints": [{"crew_id": "C102", "required_rank": "Captain",
                                     "projected_duty_minutes": 840,
                                     "max_allowed_minutes": 720, "over_limit_minutes": 120}]}
        if tool == "reserve_search":
            return {"candidates": [{"crew_id": "C345", "name": "Carol Lee", "rank": "Captain"}]}
        if tool == "validate_candidate":
            return {"crew_id": "C345", "name": "Carol Lee", "valid": not self.invalid,
                    "issues": ["qualification failed"] if self.invalid else [],
                    "checks": {"availability": True, "qualification": not self.invalid}}
        if tool == "simulate_roster_change":
            return {"safe": not self.unsafe, "read_only": True,
                    "issues": ["duty conflict"] if self.unsafe else [],
                    "proposed_removal": "C102", "proposed_replacement": "C345",
                    "checks": {"removed_crew_on_roster": True}}
        if tool == "roster_apply_change":
            return {"flight_id": arguments["flight_id"], "mock": True, "mutated": False}
        if tool == "verify_roster":
            return {"verified": True, "status": "MOCK_NO_MUTATION_CONFIRMED",
                    "actual_crew_ids": ["C102", "C231"], "mock": True, "mutated": False}
        raise AssertionError(tool)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = replace(load_settings(), event_log_path=Path(self.temp.name) / "events.jsonl",
                                mcp_api_key=None, approval_api_key=None)
        self.runbook = self.settings.runbook_path

    async def asyncTearDown(self):
        self.temp.cleanup()

    def application(self, tools=None, settings=None):
        return create_application(settings or self.settings, tool_executor=tools)

    async def pending(self, application):
        for _ in range(300):
            found = application.executions.all()
            if found and found[0].state == ExecutionState.WAITING_FOR_APPROVAL:
                return found[0]
            await asyncio.sleep(0.01)
        self.fail("run did not reach approval")

    async def test_approval_resumes_exact_action_and_verifies(self):
        tools = RecordingTools()
        application = self.application(tools)
        app, _ = create_api(application)
        run_task = asyncio.create_task(application.execution_service.execute(self.runbook, {"flight_id": "FL-1042"}))
        run = await self.pending(application)
        request = run.to_dict()
        approval = request["approval_required"]
        action = request["pending_action"]
        self.assertFalse(run_task.done())
        self.assertEqual([name for name, _ in tools.calls][-1], "simulate_roster_change")
        self.assertEqual(action["arguments"], {"flight_id": "FL-1042", "crew_to_remove": "C102", "replacement_crew_id": "C345"})
        with self.assertRaisesRegex(ValueError, "exact pending"):
            await application.approval_service.decide(run.execution_id, "approve", approval["approval_id"],
                run.execution_id, run.runbook_id, {**action, "arguments": {"flight_id": "WRONG"}})
        with self.assertRaisesRegex(ValueError, "Approval ID"):
            await application.approval_service.decide(run.execution_id, "approve", "wrong", run.execution_id, run.runbook_id, action)
        self.assertEqual(run.state, ExecutionState.WAITING_FOR_APPROVAL)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)), base_url="http://127.0.0.1") as client:
            response = await client.post(f"/runbook-approvals/{run.execution_id}", json={"decision": "approve", "approval_id": approval["approval_id"], "run_id": run.execution_id, "runbook_id": run.runbook_id, "action": action})
        self.assertEqual(response.status_code, 200, response.text)
        result = await run_task
        self.assertEqual(result["run_id"], run.execution_id)
        self.assertEqual(result["steps_completed"], 9)
        self.assertEqual(result["report"]["status"], "VERIFIED_MOCK")
        self.assertFalse(result["verification"]["roster_changed"])
        self.assertEqual([name for name, _ in tools.calls][-2:], ["roster_apply_change", "verify_roster"])
        events = [json.loads(line)["event"] for line in self.settings.event_log_path.read_text().splitlines()]
        self.assertIn("APPROVAL_RECEIVED", events)
        self.assertIn("RUN_COMPLETED", events)

    async def test_caller_cancellation_keeps_pending_run(self):
        application = self.application(RecordingTools())
        task = asyncio.create_task(application.execution_service.execute(self.runbook, {"flight_id": "FL-1042"}))
        run = await self.pending(application)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIs(application.executions.get(run.execution_id), run)
        request = run.to_dict()
        result = await application.approval_service.decide(run.execution_id, "approve", request["approval_required"]["approval_id"], run.execution_id, run.runbook_id, request["pending_action"])
        self.assertEqual(result["state"], "COMPLETED")

    async def test_approval_is_scoped_and_rejection_never_calls_mutation(self):
        tools = RecordingTools()
        application = self.application(tools)
        task = asyncio.create_task(application.execution_service.execute(self.runbook, {"flight_id": "FL-1042"}))
        run = await self.pending(application)
        request = run.to_dict()
        ticket = request["approval_required"]["approval_id"]
        action = request["pending_action"]
        for wrong_run, wrong_book, wrong_action in [
            ("other-run", run.runbook_id, action),
            (run.execution_id, "other-runbook", action),
            (run.execution_id, run.runbook_id, {**action, "step_id": "other-step"}),
            (run.execution_id, run.runbook_id, {**action, "tool": "other-tool"}),
        ]:
            with self.assertRaises(ValueError):
                await application.approval_service.decide(run.execution_id, "approve", ticket, wrong_run, wrong_book, wrong_action)
        self.assertEqual(run.state, ExecutionState.WAITING_FOR_APPROVAL)
        result = await application.approval_service.decide(run.execution_id, "reject", ticket,
            run.execution_id, run.runbook_id, action)
        self.assertEqual(result["state"], "REJECTED")
        self.assertEqual((await task)["state"], "REJECTED")
        self.assertNotIn("roster_apply_change", [name for name, _ in tools.calls])

    async def test_failures_stop_before_mutation(self):
        for tools, expected in [(RecordingTools(fail="reserve_search"), "paused"),
                                (RecordingTools(invalid=True), "blocked"),
                                (RecordingTools(unsafe=True), "blocked")]:
            with self.subTest(expected=expected, tools=tools):
                application = self.application(tools)
                result = await application.execution_service.execute(self.runbook, {"flight_id": "FL-1042"})
                self.assertEqual(result["status"], expected)
                self.assertTrue(result["no_destructive_action_attempted"])
                self.assertNotIn("roster_apply_change", [name for name, _ in tools.calls])

    async def test_backend_http_request_stays_open_until_approval(self):
        application = self.application(RecordingTools())
        app, _ = create_api(application)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
            base_url="http://127.0.0.1",
        ) as client:
            call_task = asyncio.create_task(client.post("/runbook-executions", json={"flight_id": "FL-1042"}))
            run = await self.pending(application)
            self.assertFalse(call_task.done())
            request = run.to_dict()
            approval = await client.post(f"/runbook-approvals/{run.execution_id}", json={
                "decision": "approve", "approval_id": request["approval_required"]["approval_id"],
                "run_id": run.execution_id, "runbook_id": run.runbook_id,
                "action": request["pending_action"],
            })
            self.assertEqual(approval.status_code, 200, approval.text)
            response = await call_task
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["run_id"], run.execution_id)
            self.assertEqual(response.json()["report"]["status"], "VERIFIED_MOCK")
