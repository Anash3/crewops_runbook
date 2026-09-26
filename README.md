# CrewOps Runbook

This repository has three separate projects: the CrewOps backend, a standalone FastMCP server, and a Next.js operator UI.

```text
TrueForge agent ──read-only MCP calls──► FastMCP server :8000
        │                                  │
        ├──generated Python──► sandbox     │
        │                                  │
        └──runbook_execute─────────────────┤
                                           │
                                           ▼ HTTP
                                     Backend :8001
                                     runbook engine
                                           │
                                           ▼ MCP tool calls
                                    FastMCP CrewOps tools
                                           │
                                           ▼
                                        PostgreSQL

Operator UI :3000 ──case start───────► Backend :8001
                          └──launches TrueForge turn
```

The backend owns the human-written runbook, execution state, exact-action approval, and result report. The FastMCP project owns the MCP transport, CrewOps database tools, and the `runbook_execute` proxy. The frontend calls the backend through server-side Next.js API routes. Starting a case launches a TrueForge turn, displays its real MCP and sandbox events, then links to the backend run created by that turn's `runbook_execute` call. The run page streams backend execution events and handles human approval. Both harness cases and backend executions are currently in memory, so restarting the backend loses pending and historical runs.

| Project | Main code | Entry point |
| --- | --- | --- |
| Backend | [`crewops-agent/src/crewops`](crewops-agent/src/crewops/) | [`backend_server.py`](crewops-agent/backend_server.py) |
| FastMCP | [`mcp-server/src/crewops_mcp`](mcp-server/src/crewops_mcp/) | [`serve.py`](mcp-server/serve.py) |
| Frontend | [`frontend/src`](frontend/src/) | Next.js App Router |

## Setup

Use Python 3.10 or newer, Node.js 22.14 or newer, npm, PostgreSQL, and [`uv`](https://docs.astral.sh/uv/). From a fresh clone, create and seed a local database once:

```bash
createdb crewops
psql -v ON_ERROR_STOP=1 -d crewops -f mcp-server/db/schema.sql
```

Set `DATABASE_URL` in `mcp-server/.env` to the credentials for that database. For an already initialized database, use [`mcp-server/db/seed_crew_duty_risk.sql`](mcp-server/db/seed_crew_duty_risk.sql) to prepare reserve C345; do not reapply the full schema to an existing database.

```bash
cd crewops-agent
cp .env.example .env
uv sync --locked

cd ../mcp-server
cp .env.example .env
uv sync --locked

cd ../frontend
npm ci
cp .env.local.example .env.local
```

Set `DATABASE_URL` in `mcp-server/.env`. The backend reads its own `.env`. If using authentication, set the same `MCP_API_KEY` in both projects and the same `BACKEND_API_KEY` in both projects. `RUNBOOK_APPROVAL_API_KEY` is set only in the backend and used by the human approval request.

## Run

Start the backend on port 8001:

```bash
cd crewops-agent
uv run python backend_server.py
```

Start the standalone FastMCP server on port 8000:

```bash
cd mcp-server
uv run python serve.py
```

Start TrueForge with the included script on port 8790. It sets an MCP request timeout longer than the runbook's 30-minute approval window so the original agent turn can remain open through the human decision and verification. Starting TrueForge directly with `npx` uses its shorter default timeout and may cancel the call before approval. In TrueForge Settings, configure a model provider and a [Daytona sandbox provider](https://github.com/truefoundry/trueforge/blob/main/docs/sandbox.mdx) with a key that can create snapshots and sandboxes:

```bash
cd crewops-agent
bash start_trueforge.sh
```

Start the operator UI on port 3000:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. The case intake is prefilled with an example report about `FL-1042`. Starting it creates a TrueForge session and opens `/harness/{case_id}`. That page shows actual harness MCP tool calls, returned values, sandbox code, and sandbox output. The **Harness** navigation item returns to the latest case; `/harness` lists recent case links saved in this browser. Those links remain after navigation, but the backend's in-memory case details are lost if it restarts. When the agent detects duty risk and calls `runbook_execute`, the page links to the exact backend run using the `case_id` passed through FastMCP. The run page streams a **Plan → Act → Observe** transcript over SSE from backend events, plus the operational brief, simulation diff, and exact action awaiting approval. Approve or reject on the run page; the backend resumes the same run and the original TrueForge turn receives its result. `/runs`, `/approvals`, and `/runbooks` show live backend data.

After changing backend or FastMCP code, restart **both** processes before opening a new case. An older FastMCP process may accept the agent's `case_id` argument without forwarding it, which leaves the backend run unlinked on the harness page. The Approvals page remains a way to find that pending run. Pending runs themselves are in backend memory and cannot survive a backend restart.

TrueForge can route a CrewOps call through its `call_tool` wrapper. The harness page shows the underlying CrewOps tool and arguments so `runbook_execute` remains visible. The sidebar's **Harness** link returns to the last case in this browser; `/harness` shows recent case links without needing a sessions-list API call.

The Next.js proxy uses `BACKEND_API_URL` (default `http://127.0.0.1:8001`). If backend authentication is enabled, set `BACKEND_API_KEY` and `RUNBOOK_APPROVAL_API_KEY` in `frontend/.env.local` to match the backend. Keep these keys server-side; do not use `NEXT_PUBLIC_` variables for them. The UI is a local demo and does not yet authenticate individual operators.

For a **terminal harness demo**, run the client in another terminal. The CrewOps agent enables the native sandbox; agent registration fails if no sandbox provider is available. This is a real TrueForge sandbox, separate from the read-only `simulate_roster_change` MCP tool.

```bash
cd crewops-agent
uv run python truefoundry_agent.py FL-1042
```

The agent is allowed five CrewOps MCP tools: `agent_note`, `flight_get`, `flight_roster`, `duty_clock_get`, and `runbook_execute`. `agent_note` accepts a short public update written by the model; it does not execute operations or affect approval. Watch the live agent notes, `AGENT TOOL CALL` / `TOOL RESULT` lines, and sandbox output. The agent should read FL-1042 and its crew, generate Python using the returned duty clocks, and call TrueForge's `sandbox.exec` to calculate projected duty. It invokes `runbook_execute` only when that calculation finds duty-limit risk. FastMCP sends that request to `POST /runbook-executions` on the backend and waits for the result. The backend independently runs [`crew_duty_risk_resolution.yaml`](crewops-agent/runbooks/crew_duty_risk_resolution.yaml), calling the CrewOps MCP tools for investigation, validation, simulation, mock action, and verification. The same request remains open at the approval gate. `RUNBOOK_PROXY_TIMEOUT_SECONDS`, TrueForge's `MCP_REQUEST_TIMEOUT_MS`, and the overall TrueForge turn timeout must be long enough for human approval.

### Five-minute judge walkthrough

1. Open the operator UI at `http://localhost:3000` and start the prefilled FL-1042 case.
2. On the harness page, show TrueForge making the three read-only CrewOps MCP calls and `sandbox.exec` running agent-generated Python with the live duty figures. The same session is visible in TrueForge at `http://localhost:8790`.
3. When the backend run link appears, open it. At `APPROVAL REQUESTED`, review its exact flight, crew removal, replacement, and simulation checks.
4. Click **Approve & Execute**. The pending backend run resumes; `roster_apply_change` runs in mock mode, `verify_roster` reads the unchanged roster, and the original TrueForge turn receives the completed result.
5. Return to the harness page for the final agent response and explain the boundary: the agent can read and calculate, while the backend alone owns the destructive step and exact-action approval. The mock result means this demo does not modify roster rows.

The sandbox calculation is an agent investigation aid; it cannot authorize or replace the backend's independent validation. The Harness page shows public TrueForge messages, model-authored `agent_note` calls, and actual tool results. The run page labels its scripted messages as runbook plans; those are backend events. Neither page displays private model reasoning. Model-authored progress notes depend on the model calling `agent_note`; missing notes are never filled with fabricated model text.

### What to show the judges

| Criterion | Evidence in the demo |
| --- | --- |
| Harness doing the work | The case starts a TrueForge session. Its event page shows live `flight_get`, `flight_roster`, `duty_clock_get`, generated code sent to `sandbox.exec`, and the `runbook_execute` call. |
| It actually runs | The setup above creates sample PostgreSQL data and starts all four local processes. FL-1042 has a 240-minute delay and a duty-limit risk. |
| Where it stops | The engine accepts automatic calls only for its read-tool allowlist. Its exact pending roster action is held until a human approves the run ID, action hash, and arguments. The demo action is a non-mutating mock. |
| A job worth handing over | The runbook investigates a delayed flight, finds a constrained crew member, validates a reserve, previews a substitution, and verifies the outcome. |
| Demo clarity | Keep the harness page and run page open side by side, then approve the exact action and show the final agent report. |

Current limits: the run and harness histories are in memory, the UI has no operator login, and the roster action does not write database rows. A clean-clone run and a live sandbox transcript should be captured before claiming the end-to-end demo is proven.

## Approve a run

Read the backend log's `APPROVAL REQUEST` and copy the live `run_id`, `runbook_id`, `approval_id`, and exact `pending_action`. Approve through the **backend** on port 8001:

```bash
curl -X POST "http://127.0.0.1:8001/runbook-approvals/<run_id>" \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approve","run_id":"<run_id>","runbook_id":"crew_duty_risk_resolution","approval_id":"<approval_id>","action":{"step_id":"apply_change","tool":"roster_apply_change","arguments":{"flight_id":"FL-1042","crew_to_remove":"C102","replacement_crew_id":"C345"}}}'
```

Include `Authorization: Bearer <RUNBOOK_APPROVAL_API_KEY>` when that key is configured. The engine checks the run ID, runbook ID, approval ID, step ID, tool, and full arguments before executing. After approval, it calls `roster_apply_change`, then `verify_roster`, and returns a structured operational report to the original MCP call. The roster action is still a mock: `mock=true`, `mutated=false`.

## Verify

```bash
cd crewops-agent
uv run python -m unittest discover -s tests -q

cd ../mcp-server
uv run python -m unittest discover -s tests -q

cd ..
uv run --project crewops-agent --with ./mcp-server python -m unittest discover -s integration_tests -q
```

The backend suite checks exact-action approval, rejection, caller cancellation, failure gates, and HTTP resume. The FastMCP suite checks CrewOps validation and an MCP transport call through the backend proxy. The integration suite starts both HTTP processes and verifies the complete MCP → backend → MCP → approval → verification path.

The backend core has no MCP, SQL, HTTP, or TrueFoundry imports. Runbook definitions carry a version, but execution persistence and immutable stored runbook versions remain future work. Real roster mutation also needs idempotency and operator authentication before production use. The current roster action is a mock, and the completion UI says so only when the actual result reports `mock=true` and `mutated=false`.
