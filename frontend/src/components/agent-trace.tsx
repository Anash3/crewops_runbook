"use client";

import { useEffect, useRef } from "react";
import { Activity, BookOpenCheck, BrainCircuit, Check, ChevronRight, CirclePause, Code2, Eye, LoaderCircle, Pause, Play, ShieldAlert, SkipForward, TriangleAlert, X } from "lucide-react";
import type { RunStatus, TraceEntry } from "@/lib/types";
import { stepLabel } from "@/lib/api";

const style = {
  ROUTE: { label: "Route", icon: BookOpenCheck, color: "text-[#368252]", surface: "border-[#d7e8db] bg-[#f6fbf7]" },
  PLAN: { label: "Runbook plan", icon: BrainCircuit, color: "text-[#62c58c]", surface: "border-[#29513a] bg-[#173e2a]" },
  THINK: { label: "Runbook plan", icon: BrainCircuit, color: "text-[#62c58c]", surface: "border-[#29513a] bg-[#173e2a]" },
  ACT: { label: "Act · MCP", icon: Code2, color: "text-[#4287b5]", surface: "border-[#d0e3ee] bg-[#f4f9fc]" },
  OBSERVE: { label: "Observe", icon: Eye, color: "text-[#3b875a]", surface: "border-[#d8e9dc] bg-[#f4faf5]" },
  GATE: { label: "Human approval", icon: ShieldAlert, color: "text-amber-700", surface: "border-amber-300 bg-[#fff7e7]" },
  APPROVAL: { label: "Decision", icon: Check, color: "text-[#3e875a]", surface: "border-[#d3e7d8] bg-[#f3faf4]" },
  ERROR: { label: "Tool error", icon: TriangleAlert, color: "text-rose-700", surface: "border-rose-300 bg-rose-50" },
  SKIP: { label: "Skipped", icon: CirclePause, color: "text-[#809687]", surface: "border-[#e2e9e2] bg-[#f8faf8]" },
  DONE: { label: "Outcome", icon: Activity, color: "text-[#3e875a]", surface: "border-[#d6e7da] bg-[#f2faf3]" },
} as const;

function time(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}

export function AgentTrace({ entries, totalEntries, status, connection, paused, onTogglePause, onJump }: {
  entries: TraceEntry[];
  totalEntries: number;
  status: RunStatus;
  connection: "connecting" | "live" | "reconnecting" | "complete";
  paused: boolean;
  onTogglePause: () => void;
  onJump: () => void;
}) {
  const history = useRef<HTMLDivElement>(null);
  const current = entries.at(-1);
  const previous = entries.slice(0, -1);
  const reviewing = entries.length < totalEntries;
  const currentStyle = current ? style[current.type] : null;
  const CurrentIcon = currentStyle?.icon;
  useEffect(() => { if (history.current) history.current.scrollTop = history.current.scrollHeight; }, [entries.length]);
  return <section className="overflow-hidden rounded-2xl border border-[#dce8df] bg-white shadow-[0_16px_44px_-30px_#163b2738]">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e6ede7] px-5 py-5 md:px-6"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#6b9378]">Live runbook execution</p><h2 className="mt-1 text-lg font-semibold text-[#183c2b]">Plan → Act → Observe</h2></div><div className="flex items-center gap-2"><span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-semibold ${reviewing ? "bg-sky-50 text-sky-700" : connection === "live" ? "bg-[#e9f7ed] text-[#2e7f50]" : connection === "reconnecting" ? "bg-amber-50 text-amber-700" : "bg-[#f1f5f1] text-[#718b76]"}`}><span className={`size-1.5 rounded-full ${reviewing ? "bg-sky-500" : connection === "live" ? "bg-emerald-500 animate-pulse" : connection === "reconnecting" ? "bg-amber-500" : "bg-[#9cad9e]"}`} />{reviewing ? "Reviewing recorded events" : connection === "live" ? "Streaming live" : connection === "reconnecting" ? "Reconnecting · syncing" : connection === "complete" ? "Run ended" : "Connecting"}</span></div></header>
    <div className="h-1 bg-[#eaf2eb]"><div className="h-full bg-[#65ae7b] transition-[width] duration-500" style={{ width: `${totalEntries ? Math.min(100, entries.length / totalEntries * 100) : 0}%` }} /></div>
    <div className="p-5 md:p-6">
      {current && currentStyle && CurrentIcon ? <div key={current.id} className={`trace-enter min-h-[205px] rounded-2xl border p-5 md:p-7 ${currentStyle.surface}`}>
        <div className="flex flex-wrap items-center justify-between gap-2"><div className={`flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] ${current.type === "PLAN" || current.type === "THINK" ? "text-[#a9e5bc]" : currentStyle.color}`}><CurrentIcon className="size-4" />{currentStyle.label}{current.step_id && <span className={`ml-1 normal-case tracking-normal ${current.type === "PLAN" || current.type === "THINK" ? "text-[#94bda1]" : "text-[#8ca491]"}`}>/ {stepLabel(current.step_id)}</span>}</div><time className={`font-mono text-[10px] ${current.type === "PLAN" || current.type === "THINK" ? "text-[#9cbea6]" : "text-[#9cafa0]"}`}>{time(current.timestamp)}</time></div>
        <p className={`mt-7 max-w-2xl text-lg font-medium leading-8 md:text-xl ${current.type === "PLAN" || current.type === "THINK" ? "text-white" : current.type === "GATE" ? "text-[#77501d]" : "text-[#274a35]"}`}>{current.message || (current.type === "ACT" ? "Calling CrewOps MCP…" : "Runbook event received.")}</p>
        {current.type === "ACT" && current.tool && <div className="mt-5 overflow-x-auto rounded-xl border border-[#c9dce7] bg-white px-4 py-3 font-mono text-xs leading-6 text-[#2c6286]"><span className="font-bold">{current.tool}</span>({JSON.stringify(current.arguments || {})})</div>}
        {!!current.checks?.length && <div className="mt-5 grid gap-2 sm:grid-cols-2">{current.checks.map((check) => <div key={check.key} className={`flex items-start gap-2.5 rounded-xl border px-3 py-3 ${check.passed ? "border-[#cde8d3] bg-white text-[#2f7548]" : "border-rose-200 bg-white text-rose-700"}`}><span className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full ${check.passed ? "bg-[#dcf2e1]" : "bg-rose-100"}`}>{check.passed ? <Check className="size-3.5" /> : <X className="size-3.5" />}</span><span><span className="block text-xs font-semibold">{check.label}</span>{check.detail && <span className="mt-1 block text-[11px] leading-4 text-[#809486]">{check.detail}</span>}</span></div>)}</div>}
        <div className={`mt-6 flex items-center gap-2 text-xs ${current.type === "PLAN" || current.type === "THINK" ? "text-[#a5cdb0]" : "text-[#89a192]"}`}>{current.type === "ACT" && !reviewing && status === "RUNNING" ? <LoaderCircle className="size-3.5 animate-spin" /> : <ChevronRight className="size-3.5" />}{reviewing ? "This event already happened; reviewing it in order." : current.type === "GATE" ? "Execution is stopped until a human decision." : "Following the human-written procedure."}</div>
      </div> : <div className="flex min-h-[205px] items-center gap-3 rounded-2xl border border-[#e4eee5] bg-[#f8fbf8] p-7 text-sm text-[#77927c]"><LoaderCircle className="size-4 animate-spin" /> Waiting for the first runbook event…</div>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-[#84998a]">{entries.length} of {totalEntries} updates shown{reviewing ? ` · ${totalEntries - entries.length} to review` : ""}</p><div className="flex gap-2">{reviewing && <button type="button" onClick={onTogglePause} className="inline-flex items-center gap-1.5 rounded-lg border border-[#dce9de] px-3 py-1.5 text-xs font-semibold text-[#4e785a] hover:bg-[#f3f8f4]">{paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}{paused ? "Continue" : "Pause"}</button>}{reviewing && <button type="button" onClick={onJump} className="inline-flex items-center gap-1.5 rounded-lg bg-[#e5f3e9] px-3 py-1.5 text-xs font-semibold text-[#397653] hover:bg-[#d8ecde]"><SkipForward className="size-3.5" />Jump to current</button>}</div></div>
    </div>
    {previous.length > 0 && <div className="border-t border-[#e8efe9] bg-[#fafdfa] px-5 py-4 md:px-6"><p className="mb-3 text-[10px] font-bold uppercase tracking-[0.17em] text-[#8aa08e]">Earlier updates</p><div ref={history} className="max-h-52 space-y-2 overflow-y-auto pr-1">{previous.map((entry) => { const item = style[entry.type]; const Icon = item.icon; return <div key={entry.id} className="flex items-start gap-2.5 rounded-lg bg-white px-3 py-2.5 text-xs"><Icon className={`mt-0.5 size-3.5 shrink-0 ${item.color}`} /><span className="min-w-0 flex-1 leading-5 text-[#58715e]"><span className="font-semibold text-[#3c6048]">{item.label}</span>{entry.step_id && <span className="text-[#97a99a]"> · {stepLabel(entry.step_id)}</span>}<span className="block truncate">{entry.type === "ACT" && entry.tool ? `${entry.tool}(${JSON.stringify(entry.arguments || {})})` : entry.message}</span></span><span className="font-mono text-[10px] text-[#a3b3a5]">{time(entry.timestamp)}</span></div>; })}</div></div>}
    <div className="border-t border-[#e7eee8] bg-white px-5 py-3 text-[11px] leading-5 text-[#8ba090] md:px-6">Plan entries are generated by the deterministic runbook engine from CrewOps results. TrueForge's model-authored updates appear in the linked Harness case. Review pacing changes only the display.</div>
  </section>;
}
