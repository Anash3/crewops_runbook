"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BrainCircuit, Code2, LoaderCircle, ShieldCheck, Wrench } from "lucide-react";
import { apiGet, formatTime } from "@/lib/api";
import { rememberHarnessCase } from "@/lib/harness-history";

type HarnessEvent = {
  id: number;
  type: string;
  timestamp: string;
  message?: string;
  tool?: string;
  arguments?: unknown;
  content?: string;
  status?: string;
};

type HarnessCase = {
  case_id: string;
  flight_id: string;
  issue: string;
  status: string;
  session_id: string | null;
  run_id: string | null;
  run_status: string | null;
  events: HarnessEvent[];
  error: string | null;
};

function eventTitle(event: HarnessEvent): string {
  if (event.type === "AGENT_NOTE") return "Agent update · model-authored";
  if (event.type === "AGENT_INTENT") return "Recorded intent";
  if (event.type === "TOOL_CALL") return `Call ${event.tool || "tool"}`;
  if (event.type === "TOOL_RESULT") return `Observe ${event.tool || "result"}`;
  if (event.type === "SANDBOX_CREATED") return "TrueForge sandbox created";
  if (event.type === "AGENT_MESSAGE") return "Agent observation";
  if (event.type === "SESSION_STARTED") return "TrueForge session started";
  if (event.type === "TURN_DONE") return "Agent turn finished";
  if (event.type === "ERROR") return "Harness error";
  if (event.type === "TRACE_ERROR") return "Trace display error";
  return "Assessment started";
}

export default function HarnessCasePage() {
  const { caseId } = useParams<{ caseId: string }>();
  useEffect(() => { rememberHarnessCase(caseId); }, [caseId]);
  const { data, error, isPending } = useQuery({
    queryKey: ["harness-case", caseId],
    queryFn: () => apiGet<HarnessCase>(`/api/harness-runs/${caseId}`),
    refetchInterval: (query) => {
      const current = query.state.data;
      const runStillActive = current?.run_status === "WAITING_FOR_APPROVAL" || current?.run_status === "APPROVED" || current?.run_status === "RUNNING";
      return current?.status === "STARTING" || current?.status === "RUNNING" || runStillActive || !current ? 1200 : false;
    },
  });
  useEffect(() => {
    if (data) rememberHarnessCase(caseId, data.flight_id);
  }, [caseId, data]);

  if (isPending) return <div className="flex items-center gap-2 py-16 text-sm text-[#6c8472]"><LoaderCircle className="size-4 animate-spin" /> Connecting to TrueForge…</div>;
  if (error || !data) return <div role="alert" className="rounded-xl bg-rose-50 p-6 text-sm text-rose-800">{error?.message || "Case not found"}</div>;

  const active = data.status === "STARTING" || data.status === "RUNNING";
  const invokedRunbook = data.events.some((event) => event.type === "TOOL_CALL" && event.tool?.includes("runbook_execute"));
  const called = (name: string) => data.events.some((event) => event.type === "TOOL_CALL" && event.tool?.includes(name));
  const isSandboxTool = (tool: string | undefined) => tool === "exec" || Boolean(tool?.includes("sandbox") && tool.includes("exec"));
  const sawSandbox = data.events.some((event) => event.type === "TOOL_CALL" && isSandboxTool(event.tool));
  const sandboxResponded = data.events.some((event) => event.type === "TOOL_RESULT" && isSandboxTool(event.tool));
  return <div className="mx-auto max-w-5xl space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#568773]">TrueForge assessment / {data.case_id.slice(0, 8)}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#18362b]">{data.flight_id}</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-[#627a6b]">{data.issue}</p></div>
      <span className="rounded-full border border-[#cce3d1] bg-[#eef8f0] px-3 py-1.5 text-xs font-bold text-[#32704c]">{data.status}</span>
    </div>

    {data.error && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800">{data.error}</div>}
    {data.run_id && <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-5"><div><p className="flex items-center gap-2 text-sm font-semibold text-amber-900"><ShieldCheck className="size-4" /> Human-written runbook opened</p><p className="mt-1 text-xs text-amber-800">Run {data.run_id.slice(0, 8)} · {data.run_status}. Review its exact action and approval gate.</p></div><Link href={`/runs/${data.run_id}`} className="inline-flex items-center gap-2 rounded-xl bg-[#206d4a] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#175a3c]">Open run and approval <ArrowRight className="size-4" /></Link></div>}
    {invokedRunbook && !data.run_id && active && <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-5"><div><p className="text-sm font-semibold text-amber-900">Runbook call is in progress</p><p className="mt-1 text-xs leading-5 text-amber-800">The agent is waiting for the backend result. If a pending approval does not appear here, open Approvals; the MCP server and backend must both be restarted after a code change to link the run to this case.</p></div><Link href="/approvals" className="inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-white px-4 py-2.5 text-sm font-semibold text-amber-900 hover:bg-amber-100">Check approvals <ArrowRight className="size-4" /></Link></div>}
    {active && <div className="flex items-center gap-2 text-sm text-[#51735d]">{data.run_status === "WAITING_FOR_APPROVAL" ? <><ShieldCheck className="size-4" /> TrueForge is waiting for a person. Open the linked run to review the exact action.</> : <><LoaderCircle className="size-4 animate-spin" /> TrueForge is working. Tool calls appear as they start and results appear when they return.</>}</div>}
    {data.status === "COMPLETED" && !data.run_id && <div className={`rounded-2xl border p-5 text-sm ${invokedRunbook ? "border-amber-200 bg-amber-50 text-amber-900" : "border-[#cce3d1] bg-[#eef8f0] text-[#2d6648]"}`}>{invokedRunbook ? <><p>The agent completed its runbook call, but the backend run was not linked to this case. An older MCP process may have dropped the case ID.</p><Link href="/runs" className="mt-2 inline-flex items-center gap-2 font-semibold underline">Find the completed run <ArrowRight className="size-4" /></Link></> : "The agent completed its assessment without opening a change run. Review its calculation below."}</div>}

    <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-[#dce9df] bg-white p-4 text-sm text-[#365b43]">CrewOps read tools <strong className="ml-1">{["flight_get", "flight_roster", "duty_clock_get"].filter(called).length}/3</strong></div><div className="rounded-xl border border-[#dce9df] bg-white p-4 text-sm text-[#365b43]">TrueForge sandbox <strong className="ml-1">{sandboxResponded ? "Result received" : sawSandbox ? "Call in progress" : "Not observed"}</strong></div><div className="rounded-xl border border-[#dce9df] bg-white p-4 text-sm text-[#365b43]">Runbook handoff <strong className="ml-1">{invokedRunbook ? "Called" : "Not observed"}</strong></div></div>

    <section className="rounded-2xl border border-[#dce9df] bg-white p-5 md:p-7"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#e8efe9] pb-5"><div><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#759681]">Live harness work</p><h2 className="mt-1 text-lg font-semibold text-[#17382b]">Agent update · Act · Observe</h2><p className="mt-1 text-xs text-[#819688]">Agent updates come from the model's public messages or its agent_note tool calls. Private reasoning is not shown.</p></div><span className="text-xs text-[#7d9483]">Session {data.session_id?.slice(0, 12) || "starting"}</span></div>
      <ol className="mt-5 space-y-4">{data.events.map((event) => <li key={event.id} className={`rounded-xl border p-4 ${event.type === "AGENT_NOTE" || event.type === "AGENT_MESSAGE" ? "border-[#beddeb] bg-[#f0f8fb]" : "border-[#e3ece5] bg-[#fbfdfb]"}`}><div className="flex items-center gap-2"><span className="flex size-7 items-center justify-center rounded-lg bg-[#e7f2e9] text-[#397e53]">{event.type === "AGENT_NOTE" || event.type === "AGENT_MESSAGE" ? <BrainCircuit className="size-4" /> : event.tool?.includes("exec") ? <Code2 className="size-4" /> : <Wrench className="size-4" />}</span><span className="text-sm font-semibold text-[#2f5b3e]">{eventTitle(event)}</span><span className="ml-auto text-[11px] text-[#91a396]">{formatTime(event.timestamp)}</span></div>
        {event.message && <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#486350]">{event.message}</p>}
        {event.arguments !== undefined && <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-[#10231a] p-3 text-xs leading-5 text-[#d6f3df]">{JSON.stringify(event.arguments, null, 2)}</pre>}
        {event.content && <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-[#f0f6f1] p-3 text-xs leading-5 text-[#365b43]">{event.content}</pre>}
      </li>)}</ol>
    </section>
  </div>;
}
