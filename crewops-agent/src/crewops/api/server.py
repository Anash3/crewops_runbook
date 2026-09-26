"""Backend HTTP endpoints used by the MCP adapter and human approver."""

import hmac
import json
import asyncio
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.responses import StreamingResponse
from starlette.routing import Route

from crewops.infrastructure.bootstrap import ApplicationContainer, create_application


def create_api(application: ApplicationContainer | None = None) -> tuple[Starlette, ApplicationContainer]:
    application = application or create_application()
    settings = application.settings

    def local_and_authorized(request: Request, api_key: str | None) -> JSONResponse | None:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return JSONResponse({"detail": "This endpoint is restricted to localhost"}, status_code=403)
        if api_key:
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {api_key}"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return None

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def execute(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        try:
            body = await request.json()
            flight_id = body.get("flight_id") if isinstance(body, dict) else None
            if not isinstance(flight_id, str) or not flight_id.strip():
                raise ValueError("flight_id must be a nonempty string")
            case_id = body.get("case_id")
            if case_id is not None and (
                not isinstance(case_id, str)
                or len(case_id) != 32
                or any(character not in "0123456789abcdef" for character in case_id)
            ):
                raise ValueError("case_id must be a 32-character lowercase hex ID")
            result = await application.execution_service.execute(
                settings.runbook_path,
                {
                    "flight_id": flight_id,
                    "case_id": case_id,
                    "issue": f"Crew duty risk for flight {flight_id}",
                    "selection_reason": (
                        "TrueForge preflight found a duty-limit risk."
                        if case_id else "Crew duty risk runbook requested through MCP."
                    ),
                },
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse(result)

    async def approval(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.approval_api_key)
        if denied is not None:
            return denied
        try:
            body: Any = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Approval body must be an object")
            result = await application.approval_service.decide(
                request.path_params["execution_id"],
                body.get("decision", ""),
                body.get("approval_id", ""),
                body.get("run_id", ""),
                body.get("runbook_id", ""),
                body.get("action", {}),
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse(result)

    async def start_run(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        try:
            body = await request.json()
            issue = body.get("issue") if isinstance(body, dict) else None
            if issue is None and isinstance(body, dict):
                flight_id = body.get("flight_id")
                runbook_id = body.get("runbook_id")
                if not isinstance(flight_id, str) or not flight_id.strip():
                    raise ValueError("flight_id must be a nonempty string")
                if runbook_id != settings.runbook_path.stem:
                    raise ValueError("Unknown runbook_id")
                issue = f"Crew duty risk for delayed flight {flight_id.strip()}"
            selected = application.intake_service.select(issue)
            run = application.execution_service.start(
                settings.runbook_path, {
                    "flight_id": selected.flight_id,
                    "issue": selected.issue,
                    "selection_reason": selected.selection_reason,
                }
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse(application.query_service.summary(run), status_code=201)

    async def start_harness_run(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        try:
            body = await request.json()
            issue = body.get("issue") if isinstance(body, dict) else None
            selected = application.intake_service.select(issue)
            case = application.harness_sessions.start(selected.flight_id, selected.issue)
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse({"case_id": case.case_id, "flight_id": case.flight_id, "status": case.status}, status_code=202)

    async def list_harness_runs(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        return JSONResponse({"cases": application.harness_sessions.list_cases()})

    async def get_harness_run(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        case = application.harness_sessions.get(request.path_params["case_id"])
        if case is None:
            return JSONResponse({"detail": "Harness case not found"}, status_code=404)
        execution = next(
            (
                run for run in application.executions.all()
                if run.context.get("case_id") == case.case_id
            ),
            None,
        )
        return JSONResponse({
            "case_id": case.case_id,
            "flight_id": case.flight_id,
            "issue": case.issue,
            "status": case.status,
            "session_id": case.session_id,
            "run_id": execution.execution_id if execution else None,
            "run_status": execution.state.value if execution else None,
            "events": list(case.events),
            "error": case.error,
        })

    async def list_runs(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        return denied if denied is not None else JSONResponse({"runs": application.query_service.list_runs()})

    async def get_run(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        run = application.query_service.get(request.path_params["run_id"])
        if run is None:
            return JSONResponse({"detail": "Run not found"}, status_code=404)
        return JSONResponse(application.query_service.detail(run))

    def event_name(event: dict[str, Any]) -> str:
        raw = event["event"]
        if raw == "APPROVAL_REQUESTED":
            return "APPROVAL_REQUIRED"
        if raw == "APPROVAL_RECEIVED":
            return "APPROVAL_GRANTED" if event.get("decision") == "approve" else "APPROVAL_REJECTED"
        if raw == "TOOL_CALLED" and event.get("step_id") == "apply_change":
            return "ACTION_EXECUTING"
        if raw == "ACTION_EXECUTED":
            return "ACTION_COMPLETED"
        if raw == "TOOL_CALLED" and event.get("step_id") == "verify":
            return "VERIFICATION_STARTED"
        return raw

    async def run_events(request: Request) -> StreamingResponse | JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        run = application.query_service.get(request.path_params["run_id"])
        if run is None:
            return JSONResponse({"detail": "Run not found"}, status_code=404)
        try:
            cursor = min(len(run.events), max(0, int(request.headers.get("last-event-id", "0"))))
        except ValueError:
            return JSONResponse({"detail": "Invalid Last-Event-ID"}, status_code=400)

        async def stream():
            subscriber = run.subscribe_events()
            replay = list(run.events[cursor:])
            last_sent = cursor
            try:
                for event in replay:
                    sequence = event["sequence"]
                    if sequence <= last_sent:
                        continue
                    last_sent = sequence
                    payload = {**event, "type": event_name(event), "trace_entry": application.query_service.public_trace_entry(event, sequence)}
                    yield f"id: {sequence}\nevent: run_event\ndata: {json.dumps(payload, default=str)}\n\n"
                while True:
                    if run.state.value in {"COMPLETED", "FAILED", "BLOCKED", "REJECTED"} and subscriber.empty():
                        break
                    try:
                        event = await asyncio.wait_for(subscriber.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    sequence = event["sequence"]
                    if sequence <= last_sent:
                        continue
                    last_sent = sequence
                    payload = {**event, "type": event_name(event), "trace_entry": application.query_service.public_trace_entry(event, sequence)}
                    yield f"id: {sequence}\nevent: run_event\ndata: {json.dumps(payload, default=str)}\n\n"
            finally:
                run.unsubscribe_events(subscriber)

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def list_approvals(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        return denied if denied is not None else JSONResponse({"approvals": application.query_service.approvals()})

    async def decide_ui_approval(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.approval_api_key)
        if denied is not None:
            return denied
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Approval body must be an object")
            result = await application.approval_service.decide_by_id(
                request.path_params["approval_id"],
                request.path_params["decision"],
                body.get("run_id", ""),
                body.get("action_hash", ""),
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        run = application.query_service.get(result["run_id"])
        return JSONResponse(application.query_service.detail(run) if run else result)

    async def list_runbooks(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        return JSONResponse({"runbooks": [application.query_service.runbook()]})

    async def get_runbook(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        if denied is not None:
            return denied
        if request.path_params["runbook_id"] != settings.runbook_path.stem:
            return JSONResponse({"detail": "Runbook not found"}, status_code=404)
        return JSONResponse(application.query_service.runbook())

    async def overview(request: Request) -> JSONResponse:
        denied = local_and_authorized(request, settings.backend_api_key)
        return denied if denied is not None else JSONResponse(application.query_service.overview())

    app = Starlette(routes=[
        Route("/health", health, methods=["GET"]),
        Route("/runbook-executions", execute, methods=["POST"]),
        Route("/runbook-approvals/{execution_id}", approval, methods=["POST"]),
        Route("/api/overview", overview, methods=["GET"]),
        Route("/api/runs", start_run, methods=["POST"]),
        Route("/api/harness-runs", start_harness_run, methods=["POST"]),
        Route("/api/harness-runs", list_harness_runs, methods=["GET"]),
        Route("/api/harness-runs/{case_id}", get_harness_run, methods=["GET"]),
        Route("/api/runs", list_runs, methods=["GET"]),
        Route("/api/runs/{run_id}/events", run_events, methods=["GET"]),
        Route("/api/runs/{run_id}", get_run, methods=["GET"]),
        Route("/api/approvals", list_approvals, methods=["GET"]),
        Route("/api/approvals/{approval_id}/{decision}", decide_ui_approval, methods=["POST"]),
        Route("/api/runbooks", list_runbooks, methods=["GET"]),
        Route("/api/runbooks/{runbook_id}", get_runbook, methods=["GET"]),
    ])
    return app, application


app, container = create_api()
