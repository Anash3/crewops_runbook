"""Run a TrueForge investigation that uses MCP and the native sandbox."""

import argparse
import json
import os
import uuid
from collections.abc import Callable
from typing import Any

import requests
from dotenv import load_dotenv
from crewops.infrastructure.config.settings import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

AGENT_NAME = "crewops-runbook-executor"
MCP_SERVER_NAME = "crewops"
AGENT_TOOLS = ["agent_note", "flight_get", "flight_roster", "duty_clock_get", "runbook_execute"]


def build_prompt(flight_id: str, case_id: str) -> str:
    return (
        f"Investigate flight {flight_id} using the CrewOps read tools and "
        "sandbox calculation. If the calculation finds a duty-limit risk, "
        "execute the human-written crew duty risk runbook and hold for human "
        "approval at the destructive step. When calling runbook_execute, "
        f"pass case_id={case_id} exactly so the operator can follow this run."
    )


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
        "description": "CrewOps runbook executor with an external human approval gate.",
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
    existing = next(
        (item for item in agents if item.get("name") == AGENT_NAME), None
    )

    manifest = {
        "model": {"name": model},
        "instructions": (
            "You are an operations investigator. The human-authored CrewOps "
            "runbook defines the procedure and the backend enforces all safety "
            "boundaries. The operator watches your public progress updates. "
            "Call CrewOps agent_note before each operational tool call: give one "
            "short evidence-based observation and say what you will check next "
            "and why. The first note should say you are checking the requested "
            "flight; later notes must use actual tool results and never invent "
            "evidence. These are public status updates, not private chain of "
            "thought. For a requested flight, first note, then call CrewOps flight_get, "
            "then flight_roster, then duty_clock_get for the returned crew IDs. "
            "Use the actual returned delay_minutes, total_minutes and max_allowed "
            "values to generate a short Python program and execute it with the "
            "native sandbox exec tool. The program must compute each crew member's "
            "projected duty minutes and whether projected duty exceeds the limit; "
            "print the inputs and calculated result as JSON. Do not substitute "
            "example numbers for tool results. Explain the observed risk briefly. "
            "After the sandbox result, send an agent_note with the calculated "
            "risk before deciding whether to open the runbook. "
            "If any assigned crew exceeds their duty limit, call CrewOps "
            "runbook_execute exactly once with the requested flight_id and the "
            "case_id from the user's request. If no "
            "crew exceeds the limit, report the calculation and stop without "
            "opening a change run. The runbook engine independently investigates, validates, "
            "simulates, requests human approval for its exact pending action, "
            "executes after approval and verifies. Never call roster_apply_change "
            "directly or approve your own action. Never treat sandbox calculations "
            "as authority to bypass the runbook policy. While runbook_execute is "
            "waiting, the human decides in the CrewOps UI or approval API. "
            "After it returns, use its structured report as the source of truth "
            "for WHERE, WHY, SO WHAT, proposed action, validation, approval, "
            "execution and verification. Do not invent findings or claim a mock "
            "action changed the roster. Do not make more calls after the result."
        ),
        "mcp_servers": [
            {
                "name": MCP_SERVER_NAME,
                "enable_tools": AGENT_TOOLS,
                "preload": True,
            }
        ],
        "config": {
            "iteration_limit": 24,
            "sandbox": {"enabled": True},
        },
    }
    description = "Executes the human-written CrewOps crew duty-risk runbook."
    if existing:
        # Keep platform defaults and local settings while refreshing the
        # instructions/config that this runner owns.
        updated_manifest = dict(existing.get("manifest", {}))
        updated_manifest.update(manifest)
        updated_config = dict(existing.get("manifest", {}).get("config", {}))
        updated_config.update(manifest["config"])
        updated_manifest["config"] = updated_config
        response = session.put(
            f"{base_url}/api/v1/agents/{existing['id']}",
            json={"description": description, "manifest": updated_manifest},
            timeout=30,
        )
        response_data(response)
        print(f"TRUEFORGE AGENT: {AGENT_NAME} (updated)")
        return

    response = session.post(
        f"{base_url}/api/v1/agents",
        json={
            "name": AGENT_NAME,
            "description": description,
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
    event: dict[str, Any], pending_calls: dict[int, dict[str, str]], *, complete: bool
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
            if complete:
                pending["arguments"] = arguments
            else:
                pending["arguments"] += arguments


def log_completed_tool_call(
    event: dict[str, Any], pending_calls: dict[int, dict[str, str]]
) -> str | None:
    call_id = event.get("tool_call_id", "")
    pending = next(
        (call for call in pending_calls.values() if call["id"] == call_id), None
    )
    if pending is None and len(pending_calls) == 1:
        pending = next(iter(pending_calls.values()))
    if pending is None:
        return None
    arguments: Any = pending["arguments"] or "{}"
    try:
        arguments = json.loads(arguments)
    except json.JSONDecodeError:
        pass
    print(
        "AGENT TOOL CALL: "
        + json.dumps(
            {"name": pending["name"] or "unknown", "arguments": arguments},
            ensure_ascii=False,
        ),
        flush=True,
    )
    for index, call in list(pending_calls.items()):
        if call is pending:
            del pending_calls[index]
            break
    return pending["name"] or None


def stream_turn(
    response: requests.Response,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Print the agent's tool calls, MCP results, and final explanation."""
    response.raise_for_status()
    pending_calls: dict[int, dict[str, str]] = {}
    observed_tools: set[str] = set()
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
        if on_event:
            on_event(event)

        event_type = event.get("type", "")
        if event_type in ("model.message", "model.message.delta"):
            collect_tool_calls(event, pending_calls, complete=event_type == "model.message")
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
            tool_name = log_completed_tool_call(event, pending_calls)
            if tool_name:
                observed_tools.add(tool_name)
            print(f"TOOL RESULT: {event.get('content', '')}", flush=True)
        elif event_type == "mcp.initialize":
            print("MCP CONNECTED: CrewOps server initialized", flush=True)
        elif event_type == "sandbox.created":
            print(f"SANDBOX CREATED: {event.get('sandbox_id', 'unknown')}", flush=True)
        elif event_type == "turn.done":
            state = event.get("state", {})
            output = state.get("output", {})
            if isinstance(output, dict) and output.get("content"):
                print(f"AGENT: {output['content']}", flush=True)
            print(
                "HARNESS EVIDENCE: "
                + json.dumps(
                    {
                        "mcp_reads": sorted(
                            name for name in observed_tools
                            if any(tool in name for tool in ("flight_get", "flight_roster", "duty_clock_get"))
                        ),
                        "sandbox_exec": any("exec" in name and "runbook" not in name for name in observed_tools),
                        "runbook_execute": any("runbook_execute" in name for name in observed_tools),
                    }
                ),
                flush=True,
            )
            print(f"TURN COMPLETE: {state.get('status', 'unknown')}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a TrueForge CrewOps investigation")
    parser.add_argument("flight_id", nargs="?", default="FL-1042")
    args = parser.parse_args()
    case_id = uuid.uuid4().hex
    prompt = build_prompt(args.flight_id, case_id)
    base_url = os.getenv(
        "TRUEFORGE_BASE_URL",
        os.getenv("TFY_GATEWAY_BASE_URL", "http://localhost:8790"),
    ).rstrip("/")
    mcp_url = os.getenv("CREWOPS_MCP_URL", "http://127.0.0.1:8000/mcp").rstrip("/")
    model = os.getenv("TRUEFORGE_MODEL", os.getenv("TFY_MODEL", "openai/gpt-5-6-luna"))
    turn_timeout = float(os.getenv("TRUEFORGE_TURN_TIMEOUT", "3600"))

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    print(f"Prompt: {prompt}")
    print(f"CASE ID: {case_id}")
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
            "input": [{"type": "user.message", "content": prompt}],
            "stream": True,
        },
        stream=True,
        timeout=(30, turn_timeout),
    ) as response:
        stream_turn(response)


if __name__ == "__main__":
    main()
