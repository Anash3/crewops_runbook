"""Application-scoped TrueForge sessions for the operator demo."""

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from crewops.truefoundry.agent import (
    AGENT_NAME,
    build_prompt,
    collect_tool_calls,
    ensure_agent,
    ensure_mcp_server,
    response_data,
    stream_turn,
)


@dataclass
class HarnessRun:
    case_id: str
    flight_id: str
    issue: str
    status: str = "STARTING"
    session_id: str | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    pending_calls: dict[int, dict[str, str]] = field(default_factory=dict)
    emitted_calls: set[str] = field(default_factory=set)
    streaming_message: dict[str, Any] | None = None

    def emit(self, kind: str, **details: Any) -> None:
        self.events.append({
            "id": len(self.events) + 1,
            "type": kind,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details,
        })


class HarnessSessionManager:
    """Launch TrueForge turns and retain public events for the local UI."""

    def __init__(self) -> None:
        self._runs: dict[str, HarnessRun] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    def start(self, flight_id: str, issue: str) -> HarnessRun:
        run = HarnessRun(case_id=uuid.uuid4().hex, flight_id=flight_id, issue=issue)
        self._runs[run.case_id] = run
        run.emit("CASE_STARTED", message=f"Checking {flight_id} with TrueForge")
        task = asyncio.create_task(asyncio.to_thread(self._drive, run))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    def get(self, case_id: str) -> HarnessRun | None:
        return self._runs.get(case_id)

    def list_cases(self) -> list[dict[str, Any]]:
        return [
            {
                "case_id": run.case_id,
                "flight_id": run.flight_id,
                "status": run.status,
                "session_id": run.session_id,
                "started_at": run.events[0]["timestamp"] if run.events else None,
            }
            for run in reversed(list(self._runs.values()))
        ]

    @staticmethod
    def _public_content(value: Any) -> str:
        if isinstance(value, str):
            return value[:6000]
        return json.dumps(value, ensure_ascii=False, default=str)[:6000]

    @staticmethod
    def _call_details(call: dict[str, str]) -> tuple[str, Any]:
        arguments: Any = call["arguments"] or "{}"
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            pass
        tool = call["name"]
        if tool.rsplit("__", 1)[-1] == "call_tool" and isinstance(arguments, dict):
            inner_tool = arguments.get("tool_name")
            inner_arguments = arguments.get("input")
            if isinstance(inner_tool, str) and isinstance(inner_arguments, dict):
                server = arguments.get("mcp_server")
                tool = f"{server}.{inner_tool}" if isinstance(server, str) else inner_tool
                arguments = inner_arguments
        return tool, arguments

    def _record_call(self, run: HarnessRun, call: dict[str, str]) -> None:
        tool, arguments = self._call_details(call)
        if tool.rsplit("__", 1)[-1].rsplit(".", 1)[-1] == "agent_note":
            message = arguments.get("message") if isinstance(arguments, dict) else None
            run.emit("AGENT_NOTE", tool=tool, message=message if isinstance(message, str) else "")
        else:
            run.emit("TOOL_CALL", tool=tool, arguments=arguments)
        if call["id"]:
            run.emitted_calls.add(call["id"])

    def _observe(self, run: HarnessRun, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind in {"model.message", "model.message.delta"}:
            if kind == "model.message.delta" and isinstance(event.get("content"), str) and event["content"]:
                chunk = event["content"]
                if run.streaming_message is None:
                    run.emit("AGENT_MESSAGE", content=chunk[:6000])
                    run.streaming_message = run.events[-1]
                else:
                    run.streaming_message["content"] = (run.streaming_message["content"] + chunk)[:6000]
            collect_tool_calls(
                event, run.pending_calls, complete=kind == "model.message"
            )
            if kind == "model.message":
                if event.get("content"):
                    content = self._public_content(event["content"])
                    if run.streaming_message is not None:
                        run.streaming_message["content"] = content
                    else:
                        run.emit("AGENT_MESSAGE", content=content)
                for call in run.pending_calls.values():
                    if not call["id"] or call["id"] in run.emitted_calls:
                        continue
                    self._record_call(run, call)
                run.streaming_message = None
        elif kind == "tool.response":
            call_id = event.get("tool_call_id")
            index = next(
                (index for index, call in run.pending_calls.items() if call["id"] == call_id),
                None,
            )
            if index is None and len(run.pending_calls) == 1:
                index = next(iter(run.pending_calls))
            call = run.pending_calls.pop(index, None) if index is not None else None
            if call and call["id"] not in run.emitted_calls:
                self._record_call(run, call)
            tool = self._call_details(call)[0] if call else None
            if not tool or tool.rsplit("__", 1)[-1].rsplit(".", 1)[-1] != "agent_note":
                run.emit("TOOL_RESULT", tool=tool,
                         content=self._public_content(event.get("content", "")))
        elif kind == "sandbox.created":
            run.emit("SANDBOX_CREATED", sandbox_id=event.get("sandbox_id"))
        elif kind == "turn.done":
            state = event.get("state") or {}
            result = str(state.get("status", "UNKNOWN")).lower()
            run.status = "COMPLETED" if result in {"done", "completed", "complete", "succeeded", "success"} else result.upper()
            if run.status == "ERROR":
                run.error = str(state.get("message") or "TrueForge turn failed")
            output = state.get("output") or {}
            final_content = output.get("content") if isinstance(output, dict) else None
            if final_content:
                rendered = self._public_content(final_content)
                if not any(item.get("type") == "AGENT_MESSAGE" and item.get("content") == rendered for item in run.events):
                    run.emit("AGENT_MESSAGE", content=rendered)
            run.emit("TURN_DONE", status=run.status)

    def _drive(self, run: HarnessRun) -> None:
        base_url = os.getenv(
            "TRUEFORGE_BASE_URL",
            os.getenv("TFY_GATEWAY_BASE_URL", "http://127.0.0.1:8790"),
        ).rstrip("/")
        mcp_url = os.getenv("CREWOPS_MCP_URL", "http://127.0.0.1:8000/mcp").rstrip("/")
        model = os.getenv("TRUEFORGE_MODEL", os.getenv("TFY_MODEL", "openai/gpt-5-6-luna"))
        timeout = float(os.getenv("TRUEFORGE_TURN_TIMEOUT", "3600"))
        try:
            with requests.Session() as session:
                session.headers.update({"Content-Type": "application/json"})
                ensure_mcp_server(session, base_url, mcp_url)
                ensure_agent(session, base_url, model)
                created = response_data(session.post(
                    f"{base_url}/api/v1/sessions",
                    json={"agent": {"name": AGENT_NAME}},
                    timeout=30,
                ))
                run.session_id = created.get("id")
                if not run.session_id:
                    raise RuntimeError("TrueForge did not return a session ID")
                run.status = "RUNNING"
                run.emit("SESSION_STARTED", session_id=run.session_id)
                with session.post(
                    f"{base_url}/api/v1/sessions/{run.session_id}/turns",
                    json={"input": [{"type": "user.message", "content": build_prompt(run.flight_id, run.case_id)}], "stream": True},
                    stream=True,
                    timeout=(30, timeout),
                ) as response:
                    def observe(event: dict[str, Any]) -> None:
                        try:
                            self._observe(run, event)
                        except (KeyError, TypeError, ValueError) as exc:
                            run.emit("TRACE_ERROR", message=f"Could not display one harness event: {exc}")

                    stream_turn(response, on_event=observe)
                if run.status == "RUNNING":
                    run.status = "UNKNOWN"
                    run.emit("TURN_DONE", status=run.status)
        except Exception as exc:
            run.error = str(exc)
            run.status = "FAILED"
            run.emit("ERROR", message=run.error)
