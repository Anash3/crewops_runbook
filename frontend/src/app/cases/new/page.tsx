"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, ClipboardCheck, LoaderCircle, MessageSquareText, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeading } from "@/components/page-heading";
import { apiPost } from "@/lib/api";
import { rememberHarnessCase } from "@/lib/harness-history";

const example = "FL-1042 is delayed by 240 minutes. Check whether the assigned crew can still operate the flight, and find a safe replacement if needed.";

export default function NewCasePage() {
  const router = useRouter();
  const [issue, setIssue] = useState(example);
  const start = useMutation({
    mutationFn: () => apiPost<{ case_id: string; flight_id: string }>("/api/harness-runs", { issue: issue.trim() }),
    onSuccess: (caseRun) => {
      rememberHarnessCase(caseRun.case_id, caseRun.flight_id);
      router.push(`/harness/${caseRun.case_id}`);
    },
  });
  return <div className="mx-auto max-w-5xl">
    <PageHeading eyebrow="Open a case" title="What needs attention?" description="Describe the operational situation. TrueForge checks the live CrewOps tools, calculates duty risk in its sandbox, and opens the human-written runbook when needed." />
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
      <form onSubmit={(event) => { event.preventDefault(); if (issue.trim()) start.mutate(); }} className="rounded-2xl border border-[#dce9df] bg-white p-6 shadow-[0_18px_45px_-34px_#173f292e] md:p-8">
        <div className="flex items-center gap-3"><span className="flex size-11 items-center justify-center rounded-xl bg-[#e3f3e8] text-[#267750]"><MessageSquareText className="size-5" /></span><div><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#6c9b78]">Incident intake</p><h2 className="mt-0.5 text-lg font-semibold text-[#1b3e2a]">Tell CrewOps what happened</h2></div></div>
        <label htmlFor="issue" className="mt-8 block text-xs font-semibold text-[#4c6c57]">Operational report</label>
        <textarea id="issue" value={issue} onChange={(event) => setIssue(event.target.value)} maxLength={1000} required rows={6} placeholder="e.g. FL-1042 is delayed. The assigned crew may exceed their duty limit." className="mt-2 w-full resize-y rounded-xl border border-[#d8e5db] bg-[#fbfdfb] px-4 py-3 text-sm leading-6 text-[#244533] outline-none placeholder:text-[#9aab9d] focus:border-[#68ad7b] focus:ring-2 focus:ring-[#d3edda]" />
        <div className="mt-2 flex justify-between gap-3 text-[11px] text-[#89a08d]"><span>Include a flight ID and the delay or duty concern.</span><span>{issue.length}/1000</span></div>
        {start.error && <p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{start.error.message}</p>}
        <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t border-[#eaf0ea] pt-6"><p className="max-w-xs text-xs leading-5 text-[#839789]">The harness performs the preflight. The backend owns the runbook and approval boundary.</p><Button type="submit" disabled={!issue.trim() || start.isPending} className="h-11 rounded-xl bg-[#206d4a] px-5 text-sm text-white hover:bg-[#175a3c]">{start.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}{start.isPending ? "Opening case…" : "Start TrueForge assessment"}</Button></div>
      </form>
      <aside className="rounded-2xl border border-[#d9e7d8] bg-[#eaf5eb] p-6 md:p-7"><span className="flex size-10 items-center justify-center rounded-xl bg-white text-[#367b4f]"><Sparkles className="size-5" /></span><p className="mt-6 text-[10px] font-bold uppercase tracking-[0.18em] text-[#639170]">What happens next</p><div className="mt-5 space-y-5">{[
        { icon: ClipboardCheck, title: "Choose the procedure", body: "CrewOps matches the report to a supported human-written runbook." },
        { icon: Sparkles, title: "Show the evidence", body: "Each MCP call, observation, and next decision is visible as the run advances." },
        { icon: ShieldCheck, title: "Stop at the boundary", body: "Roster actions remain blocked until a human approves the exact pending change." },
      ].map(({ icon: Icon, title, body }) => <div key={title} className="flex gap-3"><Icon className="mt-0.5 size-4 shrink-0 text-[#4c9261]" /><div><p className="text-sm font-semibold text-[#315c3b]">{title}</p><p className="mt-1 text-xs leading-5 text-[#709079]">{body}</p></div></div>)}</div><p className="mt-7 border-t border-[#d3e6d5] pt-5 text-xs leading-5 text-[#728c77]">Current supported case: delayed flight with a crew duty risk. Unsupported reports stop before runbook execution.</p></aside>
    </div>
  </div>;
}
