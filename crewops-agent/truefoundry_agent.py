"""Run the flight lookup agent through the local TrueForge API."""

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

AGENT_NAME = "crewops-runbook-executor"
MCP_SERVER_NAME = "crewops"
RUNBOOK_TOOL = "runbook_execute"
PROMPT = "Execute the delayed-flight runbook for flight FL-1042."


def response_data(response: requests.Response) -> Any:
    """Raise useful API errors and return the TrueForge response's data field."""
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"TrueForge API error: {response.text}") from exc
    payload = response.json()
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def ensure_mcp_server(session: requests.Session, base_url: str, mcp_url: str) -> None:
    response = session.get(f"{base_url}/api/v1/settings/mcp-servers", timeout=30)
    servers = response_data(response)
    existing = next(
        (item for item in servers if item.get("name") == MCP_SERVER_NAME), None
    )
    if existing:
        manifest = existing.get("manifest", {})
        if manifest.get("url") != mcp_url:
            raise RuntimeError(
                f"TrueForge MCP server {MCP_SERVER_NAME!r} already points to "
                f"{manifest.get('url')!r}, expected {mcp_url!r}"
            )
        print(f"MCP CONNECTOR: {MCP_SERVER_NAME} -> {mcp_url} (already registered)")
        return

    manifest: dict[str, Any] = {
        "type": "remote",
        "name": MCP_SERVER_NAME,
        "url": mcp_url,
        "description": "Read-only CrewOps flight status lookup.",
    }
    mcp_key = os.getenv("MCP_API_KEY")
    if mcp_key:
        manifest["auth"] = {
            "type": "header",
            "headers": {"Authorization": f"Bearer {mcp_key}"},
        }
    response = session.post(
        f"{base_url}/api/v1/settings/mcp-servers",
        json={"manifest": manifest},
        timeout=30,
    )
    response_data(response)
    print(f"MCP CONNECTOR: {MCP_SERVER_NAME} -> {mcp_url} (registered)")


def ensure_agent(
    session: requests.Session, base_url: str, model: str
) -> None:
    response = session.get(f"{base_url}/api/v1/agents", timeout=30)
    agents = response_data(response)
    if any(item.get("name") == AGENT_NAME for item in agents):
        print(f"TRUEFORGE AGENT: {AGENT_NAME} (already registered)")
        return

    manifest = {
        "model": {"name": model},
        "instructions": (
            "The human-authored CrewOps runbook defines the procedure. For a "
            "delayed-flight investigation, call only the CrewOps MCP "
            "runbook_execute tool with the requested flight_id. Do not invent, "
            "reorder, skip, or directly execute runbook steps. The executor "
            "runs reversible steps and enforces destructive-step approval. "
            "If it returns WAITING_FOR_APPROVAL, report the blocked action and "
            "do not claim it was executed or approve it yourself. Summarize "
            "completed steps and their results."
        ),
        "mcp_servers": [
            {
                "name": MCP_SERVER_NAME,
                "enable_tools": [RUNBOOK_TOOL],
                "preload": True,
            }
        ],
        "config": {"iteration_limit": 3},
    }
    response = session.post(
        f"{base_url}/api/v1/agents",
        json={
            "name": AGENT_NAME,
            "description": "Executes the human-written CrewOps delayed-flight runbook.",
            "manifest": manifest,
        },
        timeout=30,
    )
    response_data(response)
    print(f"TRUEFORGE AGENT: {AGENT_NAME} (registered, model {model})")


def event_from_payload(payload: Any) -> dict[str, Any] | None:
    """Accept either a direct event or the event envelope used by TrueForge."""
    if not isinstance(payload, dict):
        return None
    event = payload.get("event", payload)
    if isinstance(event, dict) and isinstance(event.get("event"), dict):
        event = event["event"]
    return event if isinstance(event, dict) else None


def collect_tool_calls(
    event: dict[str, Any], pending_calls: dict[int, dict[str, str]]
) -> None:
    for call in event.get("tool_calls", []):
        index = call.get("index", 0)
        pending = pending_calls.setdefault(
            index, {"id": "", "name": "", "arguments": ""}
        )
        pending["id"] = call.get("id") or pending["id"]
        function = call.get("function", {})
        info = call.get("tool_info", {})
        pending["name"] = (
            info.get("name") or function.get("name") or pending["name"]
        )
        arguments = function.get("arguments", "")
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments, ensure_ascii=False)
        if arguments:
            pending["arguments"] += arguments


def log_completed_tool_call(
    event: dict[str, Any], pending_calls: dict[int, dict[str, str]]
) -> None:
    call_id = event.get("tool_call_id", "")
    pending = next(
        (call for call in pending_calls.values() if call["id"] == call_id), None
    )
    if pending is None and len(pending_calls) == 1:
        pending = next(iter(pending_calls.values()))
    if pending is None:
        return
    arguments: Any = pending["arguments"] or "{}"
    try:
        arguments = json.loads(arguments)
    except json.JSONDecodeError:
        pass
    print(
        "MCP TOOL CALL: "
        + json.dumps(
            {"name": pending["name"] or "unknown", "arguments": arguments},
            ensure_ascii=False,
        ),
        flush=True,
    )


def stream_turn(response: requests.Response) -> None:
    """Print the agent's tool calls, MCP results, and final explanation."""
    response.raise_for_status()
    pending_calls: dict[int, dict[str, str]] = {}
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            event = event_from_payload(json.loads(raw))
        except json.JSONDecodeError:
            print(f"TRUEFORGE EVENT: {raw}", flush=True)
            continue
        if event is None:
            continue

        event_type = event.get("type", "")
        if event_type in ("model.message", "model.message.delta"):
            collect_tool_calls(event, pending_calls)
            content = event.get("content")
            if content and event_type == "model.message":
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )
                print(f"AGENT: {content}", flush=True)
        elif event_type == "tool.response":
            log_completed_tool_call(event, pending_calls)
            print(f"MCP RESULT: {event.get('content', '')}", flush=True)
        elif event_type == "mcp.initialize":
            print("MCP CONNECTED: CrewOps server initialized", flush=True)
        elif event_type == "turn.done":
            state = event.get("state", {})
            output = state.get("output", {})
            if isinstance(output, dict) and output.get("content"):
                print(f"AGENT: {output['content']}", flush=True)
            print(f"TURN COMPLETE: {state.get('status', 'unknown')}", flush=True)


def main() -> None:
    base_url = os.getenv(
        "TRUEFORGE_BASE_URL",
        os.getenv("TFY_GATEWAY_BASE_URL", "http://localhost:8790"),
    ).rstrip("/")
    mcp_url = os.getenv("CREWOPS_MCP_URL", "http://127.0.0.1:8000/mcp").rstrip("/")
    model = os.getenv("TRUEFORGE_MODEL", os.getenv("TFY_MODEL", "openai/gpt-5-6-luna"))

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    print(f"Prompt: {PROMPT}")
    print(f"TrueForge: {base_url}")
    ensure_mcp_server(session, base_url, mcp_url)
    ensure_agent(session, base_url, model)

    created = response_data(
        session.post(
            f"{base_url}/api/v1/sessions",
            json={"agent": {"name": AGENT_NAME}},
            timeout=30,
        )
    )
    session_id = created.get("id")
    if not session_id:
        raise RuntimeError(f"TrueForge did not return a session id: {created}")
    print(f"SESSION: {session_id}")

    with session.post(
        f"{base_url}/api/v1/sessions/{session_id}/turns",
        json={
            "input": [{"type": "user.message", "content": PROMPT}],
            "stream": True,
        },
        stream=True,
        timeout=(30, 300),
    ) as response:
        stream_turn(response)


if __name__ == "__main__":
    main()
