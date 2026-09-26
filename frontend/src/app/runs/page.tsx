"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { PageHeading } from "@/components/page-heading";
import { StatusBadge } from "@/components/status-badge";
import { apiGet, formatTime } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

export default function RunsPage() {
  const { data, isPending, error } = useQuery({ queryKey: ["runs"], queryFn: () => apiGet<{ runs: RunSummary[] }>("/api/runs"), refetchInterval: 5000 });
  return <div><PageHeading eyebrow="Case history" title="Runs" description="Every tool call, approval boundary, and verification stays attached to its own case." action={<Link href="/cases/new" className="inline-flex items-center gap-2 rounded-xl bg-[#206d4a] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#175a3c]"><Plus className="size-4" /> Open case</Link>} />
    {error && <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error.message}</div>}
    {isPending && <div className="rounded-2xl border bg-white p-8 text-sm text-[#819287]">Loading runs…</div>}
    {!isPending && !error && !data?.runs.length && <EmptyState title="No runs yet" description="Start with a flight to see its investigation and approval history here." />}
    {!!data?.runs.length && <div className="overflow-x-auto rounded-2xl border border-[#e1eae2] bg-white"><table className="w-full min-w-[720px] text-left"><thead className="border-b border-[#e8efe9] bg-[#f8faf8] text-[10px] font-bold uppercase tracking-[0.15em] text-[#819788]"><tr><th className="px-6 py-4">Run</th><th className="px-4 py-4">Flight</th><th className="px-4 py-4">Runbook</th><th className="px-4 py-4">Status</th><th className="px-4 py-4">Started</th><th className="px-4 py-4" /></tr></thead><tbody>{data.runs.map((run) => <tr key={run.run_id} className="border-b border-[#edf2ed] last:border-0 hover:bg-[#fafdfa]"><td className="px-6 py-4 font-mono text-xs text-[#527362]">{run.run_id.slice(0, 8)}…</td><td className="px-4 py-4 font-mono text-sm font-semibold text-[#285b3d]">{run.flight_id}</td><td className="px-4 py-4 text-sm text-[#405849]">{run.runbook_name}</td><td className="px-4 py-4"><StatusBadge status={run.status} /></td><td className="px-4 py-4 text-xs text-[#819285]">{formatTime(run.started_at)}</td><td className="px-4 py-4"><Link href={`/runs/${run.run_id}`} aria-label={`Open run ${run.run_id}`} className="flex size-8 items-center justify-center rounded-lg text-[#5c8b68] hover:bg-[#eaf5ec]"><ArrowRight className="size-4" /></Link></td></tr>)}</tbody></table></div>}
  </div>;
}
