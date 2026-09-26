"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, BookOpenCheck, Clock3, LoaderCircle, Plane } from "lucide-react";
import { ApprovalCard } from "@/components/approval-card";
import { AgentTrace } from "@/components/agent-trace";
import { CompletionCard } from "@/components/completion-card";
import { ExecutionTimeline } from "@/components/execution-timeline";
import { OperationalBrief } from "@/components/operational-brief";
import { SimulationDiff } from "@/components/simulation-diff";
import { StatusBadge } from "@/components/status-badge";
import { apiGet, formatTime } from "@/lib/api";
import type { Brief, RunDetail, TraceEntry } from "@/lib/types";

function briefAtPosition(brief: Brief, entries: TraceEntry[]): Brief {
  const observed = new Set(entries.filter((entry) => entry.type === "OBSERVE").map((entry) => entry.step_id));
  const flight = observed.has("get_flight");
  const constraint = observed.has("identify_constraint");
  const reserve = observed.has("search_reserve");
  const candidate = observed.has("validate_candidate");
  const simulation = observed.has("simulate_change");
  return {
    where: {
      flight_id: brief.where.flight_id,
      origin: flight ? brief.where.origin : undefined,
      destination: flight ? brief.where.destination : undefined,
      affected_crew_id: constraint ? brief.where.affected_crew_id : undefined,
      affected_crew_name: constraint ? brief.where.affected_crew_name : undefined,
    },
    why: {
      delay_minutes: flight ? brief.why.delay_minutes : undefined,
      constraint: constraint ? brief.why.constraint : null,
      rule: constraint ? brief.why.rule : undefined,
    },
    so_what: constraint ? brief.so_what : null,
    proposed_action: candidate ? brief.proposed_action : {},
    validation: {
      reserve_found: reserve ? brief.validation.reserve_found : null,
      candidate_valid: candidate ? brief.validation.candidate_valid : null,
      checks: candidate ? brief.validation.checks : {},
      simulation_safe: simulation ? brief.validation.simulation_safe : null,
      simulation_checks: simulation ? brief.validation.simulation_checks : {},
    },
  };
}

function readingTime(entry: TraceEntry | undefined): number {
  if (!entry) return 3200;
  if (entry.type === "OBSERVE" && entry.checks?.length) return Math.min(12000, 5000 + entry.checks.length * 450);
  const words = entry.message?.trim().split(/\s+/).length || 0;
  const minimum = entry.type === "GATE" ? 5600 : entry.type === "PLAN" || entry.type === "THINK" || entry.type === "OBSERVE" ? 4500 : entry.type === "ACT" ? 3700 : 3200;
  return Math.min(7500, Math.max(minimum, 1900 + words * 125));
}

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const queryClient = useQueryClient();
  const [streamed, setStreamed] = useState<{ runId: string; entries: TraceEntry[] }>({ runId: "", entries: [] });
  const [streamConnection, setStreamConnection] = useState<"connecting" | "live" | "reconnecting">("connecting");
  const [visibleCount, setVisibleCount] = useState(1);
  const [playbackPaused, setPlaybackPaused] = useState(false);
  const { data: run, isPending, error } = useQuery({ queryKey: ["run", runId], queryFn: () => apiGet<RunDetail>(`/api/runs/${runId}`), refetchInterval: (query) => ["RUNNING", "APPROVED", "WAITING_FOR_APPROVAL"].includes(query.state.data?.status || "") ? 3000 : false });
  const status = run?.status;
  const traceById = new Map<number, TraceEntry>((run?.trace || []).map((entry) => [entry.id, entry]));
  if (streamed.runId === runId) streamed.entries.forEach((entry) => traceById.set(entry.id, entry));
  const trace = [...traceById.values()].sort((left, right) => left.id - right.id);
  const displayedEntry = trace[visibleCount - 1];
  const displayDelay = readingTime(displayedEntry);
  const hasNextEvent = visibleCount < trace.length;
  useEffect(() => {
    if (playbackPaused || !hasNextEvent) return;
    const timer = window.setTimeout(() => setVisibleCount((current) => current + 1), displayDelay);
    return () => window.clearTimeout(timer);
  }, [visibleCount, hasNextEvent, displayDelay, playbackPaused]);
  useEffect(() => {
    if (!runId || !status || ["COMPLETED", "FAILED", "BLOCKED", "REJECTED"].includes(status)) return;
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onopen = () => setStreamConnection("live");
    source.onerror = () => setStreamConnection("reconnecting");
    source.addEventListener("run_event", (message) => {
      try {
        const event = JSON.parse((message as MessageEvent).data) as { event?: string; trace_entry?: TraceEntry | null };
        if (event.trace_entry) {
          setStreamed((previous) => ({ runId, entries: [...(previous.runId === runId ? previous.entries : []).filter((item) => item.id !== event.trace_entry!.id), event.trace_entry!] }));
        }
        if (["OBSERVATION", "APPROVAL_REQUESTED", "APPROVAL_RECEIVED", "STEP_FAILED", "STEP_SKIPPED", "RUN_COMPLETED", "RUN_BLOCKED", "RUN_FAILED", "RUN_REJECTED"].includes(event.event || "")) {
          queryClient.invalidateQueries({ queryKey: ["run", runId] });
          queryClient.invalidateQueries({ queryKey: ["overview"] });
        }
      } catch {
        queryClient.invalidateQueries({ queryKey: ["run", runId] });
      }
    });
    return () => source.close();
  }, [runId, status, queryClient]);
  if (isPending) return <div className="flex items-center gap-2 py-16 text-sm text-[#6c8472]"><LoaderCircle className="size-4 animate-spin" /> Loading execution…</div>;
  if (error || !run) return <div className="rounded-xl bg-rose-50 p-6 text-sm text-rose-800">{error?.message || "Run not found"}</div>;
  const shownTrace = trace.slice(0, visibleCount);
  const reviewing = shownTrace.length < trace.length;
  const visibleBrief = briefAtPosition(run.brief, shownTrace);
  const connection = ["COMPLETED", "FAILED", "BLOCKED", "REJECTED"].includes(run.status) ? "complete" : streamConnection;
  const route = visibleBrief.where.origin && visibleBrief.where.destination ? `${visibleBrief.where.origin} → ${visibleBrief.where.destination}` : null;
  return <div><div className="mb-5 flex flex-wrap items-center gap-5"><Link href="/runs" className="inline-flex items-center gap-2 text-xs font-semibold text-[#56836b] hover:text-[#215a3f]"><ArrowLeft className="size-4" /> All cases</Link>{run.case_id && <Link href={`/harness/${run.case_id}`} className="inline-flex items-center gap-2 text-xs font-semibold text-[#56836b] hover:text-[#215a3f]">View TrueForge MCP and sandbox work <ArrowRight className="size-4" /></Link>}</div>
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4"><div><p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#568773]">Operational case / {run.run_id.slice(0, 8)}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#18362b]">{run.runbook_name} · {run.flight_id}</h1><div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-[#6a8173]"><span className="flex items-center gap-1.5 font-mono text-[#2b6345]"><Plane className="size-4" />{run.flight_id}</span>{route && <><span className="text-[#b0c1b3]">·</span><span>{route}</span></>}<span className="text-[#b0c1b3]">·</span><span className="flex items-center gap-1.5"><Clock3 className="size-4" />{formatTime(run.started_at)}</span></div></div><StatusBadge status={run.status} /></div>
    <div className="mb-6 rounded-2xl border border-[#dce8de] bg-white p-5 md:p-6"><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#759681]">Operator report</p><p className="mt-2 text-sm leading-6 text-[#31533c]">{run.issue || `Crew duty risk for ${run.flight_id}`}</p><div className="mt-4 flex flex-wrap items-start gap-2 border-t border-[#e7eee7] pt-4 text-xs text-[#5b8068]"><BookOpenCheck className="mt-0.5 size-4 shrink-0" /><div><span className="font-semibold">Procedure selected:</span> {run.runbook_name} · v{run.runbook_version}<p className="mt-1 text-[#7c9682]">{run.selection_reason || "Selected for this supported operational case."}</p></div></div></div>
    {run.status === "COMPLETED" && !reviewing && <div className="mb-6"><CompletionCard run={run} /></div>}
    {run.status === "FAILED" || run.status === "BLOCKED" ? <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800"><strong>Run paused at {run.failure?.step_id || run.current_step || "a step"}.</strong> {run.failure?.reason || "Review the execution details before continuing."} No further action will run automatically.</div> : null}
    {run.status === "REJECTED" && <div className="mb-6 rounded-2xl border border-[#e5e7e4] bg-white p-5 text-sm text-[#647769]">This run was rejected. No roster action was executed.</div>}
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,.7fr)]"><div className="space-y-6"><AgentTrace entries={shownTrace} totalEntries={trace.length} status={run.status} connection={connection} paused={playbackPaused} onTogglePause={() => setPlaybackPaused((value) => !value)} onJump={() => { setVisibleCount(trace.length); setPlaybackPaused(false); }} />{run.simulation.available && shownTrace.some((entry) => entry.type === "OBSERVE" && entry.step_id === "simulate_change") && <SimulationDiff simulation={run.simulation} />}<details className="group rounded-2xl border border-[#dce8df] bg-white"><summary className="cursor-pointer px-5 py-4 text-sm font-semibold text-[#3c7251] marker:text-[#78a686]">View structured runbook steps and raw tool results</summary><div className="p-3 pt-0"><ExecutionTimeline steps={run.steps} /></div></details></div><div className="space-y-6">{run.approval && shownTrace.some((entry) => entry.type === "GATE") && <ApprovalCard approval={run.approval} />}<OperationalBrief brief={visibleBrief} />{run.status === "APPROVED" && !reviewing && <div className="flex items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50 p-5 text-sm text-sky-800"><LoaderCircle className="size-4 animate-spin" /> Executing approved action and verifying the result…</div>}{run.status === "COMPLETED" && !reviewing && <Link href="/cases/new" className="flex items-center justify-center gap-2 rounded-xl border border-[#cde1d2] bg-white px-4 py-3 text-sm font-semibold text-[#286747] hover:bg-[#f4faf5]">Open another case <ArrowRight className="size-4" /></Link>}</div></div>
  </div>;
}
