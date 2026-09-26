"""Validate and execute human-authored CrewOps runbooks through MCP."""

import asyncio
import json
import os
import re
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ExecutionState(str, Enum):
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunbookStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    destructive: bool
    timeout: float = Field(default=30.0, gt=0)


class Runbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    steps: list[RunbookStep] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_step_ids(self) -> "Runbook":
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Runbook step IDs must be unique")
        return self


class MCPClient:
    """Small async client for the CrewOps Streamable HTTP MCP server."""

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self.url = url
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    async def _call(self, tool: str, arguments: dict[str, Any], timeout: float) -> Any:
        async def invoke() -> Any:
            async with streamablehttp_client(self.url, headers=self.headers) as (
                read_stream,
                write_stream,
                _,
            ):
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
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"MCP tool {tool} exceeded {timeout:g}s") from exc

    async def call(self, tool: str, arguments: dict[str, Any], timeout: float) -> Any:
        return await self._call(tool, arguments, timeout)


_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(.*)\}$")
_PATH_PART = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")


def _resolve_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    match = _REFERENCE.fullmatch(value)
    if not match:
        return value

    resolved: Any = context[match.group(1)]
    suffix = match.group(2)
    consumed = 0
    for part in _PATH_PART.finditer(suffix):
        if part.start() != consumed:
            raise ValueError(f"Invalid runbook output reference: {value}")
        consumed = part.end()
        resolved = resolved[part.group(1)] if part.group(1) else resolved[int(part.group(2))]
    if consumed != len(suffix):
        raise ValueError(f"Invalid runbook output reference: {value}")
    return resolved


def load_runbook(path: Path) -> Runbook:
    """Load YAML and validate it against the runbook schema."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Runbook.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
        raise ValueError(f"Could not load valid runbook {path.name}: {exc}") from exc


class RunbookExecution:
    """Executor with an engine-owned approval gate for destructive steps."""

    DESTRUCTIVE_TOOLS = {"dangerous_test_action", "roster_apply_change"}
    MOCK_TOOLS = {"dangerous_test_action"}

    def __init__(
        self,
        runbook: Runbook,
        mcp_client: MCPClient,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        self.runbook = runbook
        self.execution_id = uuid.uuid4().hex
        self.mcp_client = mcp_client
        self.context: dict[str, Any] = dict(inputs or {})
        self.step_results: list[dict[str, Any]] = []
        self.state = ExecutionState.RUNNING
        self.step_index = 0
        self.pending_step: RunbookStep | None = None

    def _is_destructive(self, step: RunbookStep) -> bool:
        return step.destructive or step.tool in self.DESTRUCTIVE_TOOLS

    async def execute_step(self, step: RunbookStep) -> dict[str, Any] | None:
        """Execute one step, or stop before its tool call pending approval."""
        destructive = self._is_destructive(step)
        if destructive and not (
            self.state == ExecutionState.APPROVED and self.pending_step == step
        ):
            self.state = ExecutionState.WAITING_FOR_APPROVAL
            self.pending_step = step
            print("🛑 Approval required", flush=True)
            print(f"Action: {step.tool}", flush=True)
            print("Execution has been blocked.", flush=True)
            return None

        arguments = _resolve_value(step.arguments, self.context)
        print(f"RUNBOOK STEP: {step.id} -> {step.tool}", flush=True)
        if step.tool in self.MOCK_TOOLS:
            result: Any = {
                "action": step.tool,
                "flight_id": arguments.get("flight_id"),
                "mock": True,
                "executed": True,
            }
        else:
            result = await self.mcp_client.call(step.tool, arguments, step.timeout)
        print(f"✓ {step.id}", flush=True)
        return result

    async def run(self) -> dict[str, Any]:
        if self.state not in (ExecutionState.RUNNING, ExecutionState.APPROVED):
            raise RuntimeError(f"Cannot run execution in state {self.state.value}")

        while self.step_index < len(self.runbook.steps):
            step = self.runbook.steps[self.step_index]
            try:
                result = await self.execute_step(step)
            except Exception as exc:
                self.state = ExecutionState.FAILED
                self.step_results.append(
                    {"step_id": step.id, "status": "FAILED", "error": str(exc)}
                )
                print(f"✗ {step.id}: {exc}", flush=True)
                return self.to_dict()

            if result is None and self.state == ExecutionState.WAITING_FOR_APPROVAL:
                return self.to_dict()

            self.context[step.id] = result
            step_result = {
                "step_id": step.id,
                "tool": step.tool,
                "status": "COMPLETED",
                "result": result,
            }
            if self.state == ExecutionState.APPROVED:
                step_result["approval"] = ExecutionState.APPROVED.value
            self.step_results.append(step_result)
            self.step_index += 1
            if self.state == ExecutionState.APPROVED:
                self.state = ExecutionState.RUNNING
                self.pending_step = None

        self.state = ExecutionState.COMPLETED
        return self.to_dict()

    async def approve_pending(self) -> dict[str, Any]:
        """Explicit host-side approval; this method is not an agent tool."""
        if self.state != ExecutionState.WAITING_FOR_APPROVAL or self.pending_step is None:
            raise RuntimeError("There is no destructive step waiting for approval")
        self.state = ExecutionState.APPROVED
        return await self.run()

    def reject_pending(self) -> dict[str, Any]:
        """Explicit host-side rejection; this method is not an agent tool."""
        if self.state != ExecutionState.WAITING_FOR_APPROVAL:
            raise RuntimeError("There is no destructive step waiting for approval")
        if self.pending_step is not None:
            self.step_results.append(
                {
                    "step_id": self.pending_step.id,
                    "tool": self.pending_step.tool,
                    "status": ExecutionState.REJECTED.value,
                }
            )
        self.state = ExecutionState.REJECTED
        self.pending_step = None
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "execution_id": self.execution_id,
            "runbook": self.runbook.name,
            "state": self.state.value,
            "steps": self.step_results,
        }
        if self.pending_step is not None and self.state == ExecutionState.WAITING_FOR_APPROVAL:
            payload["approval_required"] = {
                "step_id": self.pending_step.id,
                "action": self.pending_step.tool,
                "arguments": _resolve_value(self.pending_step.arguments, self.context),
                "message": "Execution has been blocked.",
                "approval_endpoint": f"/runbook-approvals/{self.execution_id}",
            }
        return payload


PENDING_RUNBOOK_EXECUTIONS: dict[str, RunbookExecution] = {}


async def execute_runbook(
    runbook_path: Path,
    mcp_url: str,
    flight_id: str,
    mcp_api_key: str | None = None,
) -> dict[str, Any]:
    """Load the human-authored runbook and execute its safe prefix."""
    runbook = load_runbook(runbook_path)
    client = MCPClient(mcp_url, api_key=mcp_api_key)
    execution = RunbookExecution(runbook, client, inputs={"flight_id": flight_id})
    result = await execution.run()
    if execution.state == ExecutionState.WAITING_FOR_APPROVAL:
        PENDING_RUNBOOK_EXECUTIONS[execution.execution_id] = execution
    return result


async def decide_approval(execution_id: str, decision: str) -> dict[str, Any]:
    """Apply a host-side decision to a pending execution; never an agent tool."""
    execution = PENDING_RUNBOOK_EXECUTIONS.get(execution_id)
    if execution is None:
        raise ValueError(f"No pending runbook execution {execution_id}")
    if decision == "approve":
        result = await execution.approve_pending()
    elif decision == "reject":
        result = execution.reject_pending()
    else:
        raise ValueError("decision must be 'approve' or 'reject'")
    if execution.state != ExecutionState.WAITING_FOR_APPROVAL:
        PENDING_RUNBOOK_EXECUTIONS.pop(execution_id, None)
    return result
