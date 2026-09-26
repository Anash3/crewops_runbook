"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ShieldAlert } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { PageHeading } from "@/components/page-heading";
import { apiGet, formatTime } from "@/lib/api";
import type { Approval, RunSummary } from "@/lib/types";

export default function ApprovalsPage() {
  const { data, isPending, error } = useQuery({ queryKey: ["approvals"], queryFn: () => apiGet<{ approvals: Array<{ run: RunSummary; approval: Approval }> }>("/api/approvals"), refetchInterval: 5000 });
  return <div><PageHeading eyebrow="Human control" title="Pending approvals" description="Each approval applies only to the exact action shown in its run." />
    {error && <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error.message}</div>}
    {isPending && <div className="rounded-2xl border bg-white p-8 text-sm text-[#819287]">Loading approvals…</div>}
    {!isPending && !error && !data?.approvals.length && <EmptyState title="No approvals pending" description="Runs that reach a destructive step will appear here for review." action={false} />}
    <div className="grid gap-4 md:grid-cols-2">{data?.approvals.map(({ run, approval }) => <Link key={approval.approval_id} href={`/runs/${run.run_id}`} className="group rounded-2xl border border-[#ebd8ad] bg-white p-6 shadow-[0_10px_25px_-20px_#715529] hover:border-[#d4ad62] hover:shadow-lg"><div className="flex items-start justify-between"><span className="flex size-10 items-center justify-center rounded-xl bg-amber-100 text-amber-700"><ShieldAlert className="size-5" /></span><ArrowRight className="size-4 text-[#9b814d] transition-transform group-hover:translate-x-1" /></div><p className="mt-5 font-mono text-lg font-semibold text-[#2c523a]">{run.flight_id}</p><p className="mt-1 text-sm text-[#657e6b]">{run.runbook_name}</p><div className="mt-5 rounded-xl bg-[#faf8f0] px-4 py-3 font-mono text-sm text-[#5a6448]"><span className="text-rose-700">{approval.arguments.crew_to_remove}</span> → <span className="text-emerald-700">{approval.arguments.replacement_crew_id}</span></div><p className="mt-4 text-xs text-[#9a8b6b]">Review before {formatTime(approval.expires_at)}</p></Link>)}</div>
  </div>;
}
