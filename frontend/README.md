# CrewOps Operator UI

Next.js, TypeScript, Tailwind, shadcn/ui, Lucide, and TanStack Query frontend for the separate CrewOps backend.

## Run locally

Start the backend, FastMCP server, and TrueForge as described in the repository [README](../README.md). Then:

```bash
npm ci
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`. The case report is prefilled with the `FL-1042` delay scenario. Submitting it starts a TrueForge session and opens `/harness/{case_id}`, which shows its public model updates, real MCP calls, and sandbox output. If the agent finds a duty risk, it invokes the human-written runbook and links to `/runs/{run_id}`. The run page streams Plan → Act → Observe events over SSE and replays them after reconnect. It presents one recorded event at a time, with pause and jump-to-current controls when the backend has already advanced. This pacing affects only the display. Plan entries are backend summaries, while the Harness page shows public model-authored updates when the model emits them. The exact MCP call, observed tool result, structured step view, brief, and simulation come from actual run data. At `WAITING_FOR_APPROVAL`, the backend provides the exact pending action and action hash. The UI sends a human decision to the backend; only the backend can release the approval gate. Reports outside the supported delay or duty-risk scenario are rejected before a run starts.

The investigation uses real CrewOps MCP reads and validation. `roster_apply_change` is still a mock tool: the runbook declares it as such, the approval card labels it, and completion reports its actual `mock` and `mutated` fields.

Routes: `/cases/new`, `/harness`, `/harness/{case_id}`, `/runs`, `/runs/{run_id}`, `/approvals`, and `/runbooks`. `/investigate` redirects to `/cases/new`; `/app` remains an optional overview.

## Configuration

`BACKEND_API_URL` defaults to `http://127.0.0.1:8001`. Set `BACKEND_API_KEY` and `RUNBOOK_APPROVAL_API_KEY` to match the backend if those keys are enabled. The Next.js API proxy keeps the keys on the server. There is no operator identity or role system in this local MVP.

Active runs are stored in backend memory. Restarting the backend clears them. The roster change remains a mock; a completed mock run is shown as a verified simulation, not as a production roster change.
