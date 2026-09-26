# CrewOps Runbook Executor

This project runs a human-authored flight runbook through a local TrueFoundry agent and the CrewOps MCP server. The Python executor validates the YAML, invokes reversible CrewOps tools through MCP, and pauses before the destructive mock action until a human decides.

## Setup

The application lives in [`crewops-agent/`](crewops-agent/). It needs Python 3.10 or newer, [`uv`](https://docs.astral.sh/uv/), PostgreSQL, and a local TrueFoundry runtime available at `http://localhost:8790` with a model provider configured.

```bash
cd crewops-agent
[ -f .env ] || cp .env.example .env
uv sync --locked
```

Set `DATABASE_URL` in `.env` to your PostgreSQL connection string. Initialize an empty database once by running [`db/schema.sql`](crewops-agent/db/schema.sql) with your PostgreSQL client. The schema includes sample flight, crew, roster, and duty-clock rows for FL-1042. Configure the model provider in TrueFoundry; `TRUEFORGE_MODEL` in `.env` selects the model used to register the agent.

## Run

Start the MCP server in one terminal:

```bash
cd crewops-agent
uv run python crewops_mcp_server.py
```

In another terminal, run the TrueForge agent:

```bash
cd crewops-agent
uv run python truefoundry_agent.py
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. The agent registers the `crewops` MCP server and `crewops-runbook-executor` agent with TrueFoundry if they do not already exist, then starts a turn to execute the human-authored [`runbooks/crew_delay_resolution.yaml`](crewops-agent/runbooks/crew_delay_resolution.yaml) for FL-1042. The runbook completes `flight_get`, `flight_roster`, and `duty_clock_get`, then pauses at `dangerous_test_action`. This action is a local mock; no roster mutation is implemented.

## Human approval

The pending result includes an `execution_id`. Approval decisions go to the localhost HTTP endpoint, which is separate from the MCP tools exposed to the agent:

```bash
curl -X POST "http://127.0.0.1:8000/runbook-approvals/<execution_id>" \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approve"}'
```

The approval response includes the executor state and step results. Approving runs the pending action and continues to the runbook's verification step; rejecting marks the pending step rejected. If `RUNBOOK_APPROVAL_API_KEY` is set in `.env`, include its bearer token on the request:

```bash
-H 'Authorization: Bearer <RUNBOOK_APPROVAL_API_KEY>'
```

Approval requests are restricted to localhost. Pending approval state is held in memory by the MCP server and is cleared if the server restarts.
