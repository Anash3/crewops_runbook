"use client";

import { useState } from "react";
import { Check, ChevronDown, Circle, Code2, LoaderCircle, ShieldAlert, X } from "lucide-react";
import type { RunStep } from "@/lib/types";
import { stepLabel } from "@/lib/api";

function StepIcon({ status }: { status: string }) {
  if (status === "COMPLETED") return <Check className="size-4" strokeWidth={2.8} />;
  if (status === "WAITING_FOR_APPROVAL") return <ShieldAlert className="size-4" />;
  if (["FAILED", "BLOCKED", "REJECTED"].includes(status)) return <X className="size-4" />;
  if (status === "RUNNING") return <LoaderCircle className="size-4 animate-spin" />;
  return <Circle className="size-3" />;
}

export function ExecutionTimeline({ steps }: { steps: RunStep[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const completed = steps.filter((step) => step.status === "COMPLETED").length;
  return <section className="overflow-hidden rounded-2xl border border-[#dce8df] bg-white shadow-[0_10px_32px_-24px_#18382d30]">
    <header className="flex items-center justify-between gap-4 border-b border-[#e7eee8] px-6 py-5"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#638773]">Evidence trail</p><h2 className="mt-1 text-lg font-semibold text-[#17382b]">Execution, step by step</h2></div><span className="rounded-full bg-[#edf5ee] px-3 py-1.5 font-mono text-xs font-semibold text-[#417152]">{completed} / {steps.length}</span></header>
    <ol className="p-4 md:p-6">{steps.map((step, index) => {
      const complete = step.status === "COMPLETED";
      const waiting = step.status === "WAITING_FOR_APPROVAL";
      const active = step.status === "RUNNING";
      const failed = ["FAILED", "BLOCKED", "REJECTED"].includes(step.status);
      const current = expanded === step.id;
      return <li key={step.id} className="relative flex gap-3 pb-4 last:pb-0 md:gap-4">
        {index !== steps.length - 1 && <span className="absolute left-[15px] top-9 bottom-0 w-px bg-[#dce9df]" />}
        <div className={`relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border ${complete ? "border-[#bde4ca] bg-[#e4f5e9] text-[#228152]" : waiting ? "border-amber-300 bg-amber-100 text-amber-700" : failed ? "border-red-300 bg-red-100 text-red-700" : active ? "border-sky-300 bg-sky-100 text-sky-700" : "border-[#e2e9e3] bg-[#f7faf7] text-[#a3b2a8]"}`}><StepIcon status={step.status} /></div>
        <div className={`min-w-0 flex-1 rounded-xl border px-4 py-4 ${waiting ? "border-amber-300 bg-[#fffbf2]" : failed ? "border-rose-200 bg-rose-50" : active ? "border-sky-200 bg-sky-50/50" : "border-[#e6ede6] bg-white"}`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2.5"><span className="font-mono text-[10px] font-semibold text-[#93a899]">{String(index + 1).padStart(2, "0")}</span><h3 className={`text-sm font-semibold ${step.status === "PENDING" ? "text-[#85998a]" : "text-[#254732]"}`}>{stepLabel(step.id)}</h3></div><span className={`text-[10px] font-bold uppercase tracking-[0.12em] ${waiting ? "text-amber-700" : failed ? "text-rose-700" : complete ? "text-[#4e8f61]" : "text-[#96a79a]"}`}>{waiting ? "Approval gate" : step.status === "RUNNING" ? "In progress" : step.status.toLowerCase().replaceAll("_", " ")}</span></div>
          <p className="mt-2 text-xs leading-5 text-[#748c79]">{step.description}</p>
          {(step.arguments || active || waiting) && <div className={`mt-4 rounded-lg border px-3 py-2.5 ${waiting ? "border-amber-200 bg-white" : "border-[#e8eee8] bg-[#f8faf8]"}`}><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-[#7c9983]"><Code2 className="size-3.5" />{waiting ? "Blocked MCP call" : active ? "MCP call in progress" : "MCP call"}</div><div className="mt-1.5 break-all font-mono text-[11px] leading-5 text-[#3c684b]"><span className="font-semibold">{step.tool}</span>({step.arguments ? JSON.stringify(step.arguments) : "…"})</div></div>}
          {step.observation && <div className="mt-4 grid gap-3 border-t border-[#e7eee7] pt-4 sm:grid-cols-2"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#73947b]">Observed</p><p className="mt-1.5 text-xs leading-5 text-[#35533f]">{step.observation}</p></div>{step.next_decision && <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#73947b]">Decision / next</p><p className="mt-1.5 text-xs leading-5 text-[#35533f]">{step.next_decision}</p></div>}</div>}
          {waiting && <p className="mt-4 rounded-lg bg-amber-100 px-3 py-2 text-xs font-semibold text-amber-800">Execution is stopped. This tool has not been called.</p>}
          {step.reason && <p className="mt-3 text-xs text-rose-700">{step.reason}</p>}
          {step.result !== null && <div className="mt-3"><button type="button" onClick={() => setExpanded(current ? null : step.id)} aria-expanded={current} className="flex items-center gap-1 text-[11px] font-semibold text-[#4f855f] hover:text-[#245c39]">{current ? "Hide" : "View"} tool response <ChevronDown className={`size-3.5 transition-transform ${current ? "rotate-180" : ""}`} /></button>{current && <pre className="mt-3 max-h-72 overflow-auto rounded-lg bg-[#142a20] p-4 font-mono text-[11px] leading-5 text-[#d6efdf]">{JSON.stringify(step.result, null, 2)}</pre>}</div>}
        </div>
      </li>;
    })}</ol>
  </section>;
}
