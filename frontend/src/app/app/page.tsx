"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Clock3, Plus, ShieldAlert } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { PageHeading } from "@/components/page-heading";
import { StatusBadge } from "@/components/status-badge";
import { apiGet, formatTime } from "@/lib/api";
import type { Overview } from "@/lib/types";

export default function OverviewPage() {
  const { data, isPending, error } = useQuery({ queryKey: ["overview"], queryFn: () => apiGet<Overview>("/api/overview"), refetchInterval: 5000 });
  const stats = [
    { label: "Active runs", value: data?.active_runs, icon: Clock3, tone: "bg-sky-50 text-sky-700" },
    { label: "Awaiting approval", value: data?.awaiting_approval, icon: ShieldAlert, tone: "bg-amber-50 text-amber-700" },
    { label: "Completed today", value: data?.completed_today, icon: CheckCircle2, tone: "bg-emerald-50 text-emerald-700" },
  ];
  return <div><PageHeading eyebrow="Operational control center" title="Overview" description="Monitor open cases, review gated actions, and follow each run to verification." action={<Link href="/cases/new" className="inline-flex items-center gap-2 rounded-xl bg-[#206d4a] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#175a3c]"><Plus className="size-4" /> Open case</Link>} />
    <div className="mb-8 rounded-2xl bg-[#193e2c] px-7 py-8 text-white md:px-9 md:py-10"><p className="text-[10px] font-bold uppercase tracking-[0.23em] text-[#9bd3ad]">Crew operations</p><h2 className="mt-3 max-w-xl text-2xl font-semibold tracking-tight md:text-3xl">Every operational decision, visible from case intake to verification.</h2><p className="mt-3 max-w-xl text-sm leading-6 text-[#bbd6c3]">Describe the situation. The backend selects a supported runbook and pauses before any roster action.</p><Link href="/cases/new" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#c5efd3] px-4 py-2.5 text-sm font-semibold text-[#1c5939] hover:bg-white">Open a case <ArrowRight className="size-4" /></Link></div>
    {error && <div className="mb-6 rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error.message}</div>}
    <div className="mb-9 grid gap-4 sm:grid-cols-3">{stats.map(({ label, value, icon: Icon, tone }) => <div key={label} className="rounded-2xl border border-[#e1eae2] bg-white p-5"><div className={`flex size-10 items-center justify-center rounded-xl ${tone}`}><Icon className="size-5" /></div><div className="mt-5 text-3xl font-semibold tracking-tight text-[#214131]">{isPending ? "—" : value ?? 0}</div><p className="mt-1 text-xs font-medium text-[#829387]">{label}</p></div>)}</div>
    <div className="mb-4 flex items-center justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#75917f]">Activity</p><h2 className="mt-1 text-xl font-semibold text-[#254633]">Recent investigations</h2></div><Link href="/runs" className="flex items-center gap-1.5 text-xs font-semibold text-[#347a54]">View all <ArrowRight className="size-4" /></Link></div>
    {!isPending && !error && !data?.recent_runs.length && <EmptyState title="No investigations yet" description="Your recent operational investigations will appear here." />}
    {!!data?.recent_runs.length && <div className="overflow-hidden rounded-2xl border border-[#e1eae2] bg-white">{data.recent_runs.map((run) => <Link key={run.run_id} href={`/runs/${run.run_id}`} className="flex flex-wrap items-center gap-4 border-b border-[#eef2ed] px-6 py-5 last:border-0 hover:bg-[#fafdfa]"><span className="flex size-10 items-center justify-center rounded-xl bg-[#edf6ee] font-mono text-xs font-bold text-[#3e8154]">{run.flight_id?.slice(-4)}</span><span className="min-w-0 flex-1"><span className="block font-mono text-sm font-semibold text-[#2f5d3c]">{run.flight_id}</span><span className="mt-0.5 block text-xs text-[#839587]">{run.runbook_name} · {formatTime(run.started_at)}</span></span><StatusBadge status={run.status} /><ArrowRight className="size-4 text-[#7fa387]" /></Link>)}</div>}
  </div>;
}
