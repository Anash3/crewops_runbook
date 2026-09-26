"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, LoaderCircle, ShieldAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiPost, formatTime } from "@/lib/api";
import type { Approval, RunDetail } from "@/lib/types";

export function ApprovalCard({ approval, onDecision }: { approval: Approval; onDecision?: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const decision = useMutation({
    mutationFn: (choice: "approve" | "reject") => apiPost<RunDetail>(`/api/approvals/${approval.approval_id}/${choice}`, { run_id: approval.run_id, action_hash: approval.action_hash }),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey: ["run", approval.run_id] }); queryClient.invalidateQueries({ queryKey: ["approvals"] }); queryClient.invalidateQueries({ queryKey: ["runs"] }); queryClient.invalidateQueries({ queryKey: ["overview"] }); onDecision?.(); },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Approval request failed"),
  });
  const args = approval.arguments;
  const checks = approval.proposal.simulation_checks || {};
  return <section className="overflow-hidden rounded-2xl border-2 border-[#e5b96c] bg-white shadow-[0_18px_45px_-28px_#9c6a23]">
    <div className="flex items-center gap-3 bg-[#fff7e7] px-6 py-4 text-[#8e5d1c]"><span className="flex size-9 items-center justify-center rounded-xl bg-[#ffe7b0]"><ShieldAlert className="size-5" /></span><div><p className="text-xs font-bold uppercase tracking-[0.16em]">Human approval required</p><p className="mt-0.5 text-xs text-[#9a7640]">The runbook is paused before a controlled roster action.</p></div></div>
    <div className="p-6"><h3 className="text-lg font-semibold text-[#243f30]">{approval.proposal.mock_action ? "Proposed substitution preview" : "Proposed roster change"}</h3><div className="mt-5 grid grid-cols-3 gap-3 rounded-xl border border-[#e5ece5] bg-[#f8faf7] p-4"><div><p className="text-[10px] font-semibold uppercase tracking-wide text-[#889d8d]">Flight</p><p className="mt-1 font-mono text-sm font-semibold text-[#244835]">{args.flight_id || "—"}</p></div><div><p className="text-[10px] font-semibold uppercase tracking-wide text-[#889d8d]">Remove</p><p className="mt-1 font-mono text-sm font-semibold text-rose-700">{args.crew_to_remove || "—"}</p></div><div><p className="text-[10px] font-semibold uppercase tracking-wide text-[#889d8d]">Add</p><p className="mt-1 font-mono text-sm font-semibold text-emerald-700">{args.replacement_crew_id || "—"}</p></div></div>
      {Object.keys(checks).length > 0 && <div className="mt-5"><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#769380]">Simulation checks</p><div className="mt-3 flex flex-wrap gap-2">{Object.entries(checks).map(([name, passed]) => <span key={name} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${passed ? "bg-[#eaf6ed] text-[#347f50]" : "bg-rose-50 text-rose-700"}`}>{passed ? <Check className="size-3.5" /> : <X className="size-3.5" />}{name.replaceAll("_", " ")}</span>)}</div></div>}
      {approval.proposal.mock_action && <p className="mt-5 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-800">Scenario preview: approval will run the proposed substitution through the controlled workflow. Stored crew assignments will remain unchanged.</p>}
      <p className="mt-5 flex gap-2 text-xs leading-5 text-[#9a6d31]"><AlertTriangle className="mt-0.5 size-4 shrink-0" />Approval is tied to this run and these exact tool arguments. Expires {formatTime(approval.expires_at)}.</p>
      {error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-800">{error}</p>}
      <div className="mt-6 flex flex-wrap gap-3"><Button variant="outline" disabled={decision.isPending} onClick={() => decision.mutate("reject")} className="min-w-32 rounded-xl border-[#d5ddd5]">Reject</Button><Button disabled={decision.isPending} onClick={() => decision.mutate("approve")} className="min-w-44 rounded-xl bg-[#206d4a] text-white hover:bg-[#165a3c]">{decision.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Check className="size-4" />}{decision.isPending ? "Submitting…" : approval.proposal.mock_action ? "Approve preview" : "Approve & execute"}</Button></div>
    </div>
  </section>;
}
