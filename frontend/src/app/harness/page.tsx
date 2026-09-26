"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Cpu, Plus } from "lucide-react";
import { formatTime } from "@/lib/api";
import { EmptyState } from "@/components/empty-state";
import { PageHeading } from "@/components/page-heading";
import { recentHarnessCases, type RecentHarnessCase } from "@/lib/harness-history";

export default function HarnessRunsPage() {
  const [cases, setCases] = useState<RecentHarnessCase[] | null>(null);
  useEffect(() => { setCases(recentHarnessCases()); }, []);
  return <div>
    <PageHeading eyebrow="TrueForge activity" title="Harness sessions" description="Return to the agent's MCP calls, sandbox output, and linked runbook for a case opened in this browser." action={<Link href="/cases/new" className="inline-flex items-center gap-2 rounded-xl bg-[#206d4a] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#175a3c]"><Plus className="size-4" /> Open case</Link>} />
    {cases === null && <div className="rounded-2xl border bg-white p-8 text-sm text-[#819287]">Loading recent cases…</div>}
    {cases?.length === 0 && <EmptyState title="No harness sessions yet" description="Open a case to watch TrueForge use CrewOps tools and its sandbox." />}
    {!!cases?.length && <div className="space-y-3">{cases.map((item) => <Link key={item.case_id} href={`/harness/${item.case_id}`} className="flex flex-wrap items-center gap-4 rounded-2xl border border-[#dce9df] bg-white p-5 hover:border-[#9ac7a7] hover:bg-[#fafdfa]"><span className="flex size-10 items-center justify-center rounded-xl bg-[#e9f5ec] text-[#3b8055]"><Cpu className="size-5" /></span><div className="min-w-[180px] flex-1"><p className="text-sm font-semibold text-[#274e37]">{item.flight_id || "TrueForge case"}</p><p className="mt-1 font-mono text-xs text-[#83998a]">{item.case_id.slice(0, 8)}</p></div><span className="text-xs text-[#83998a]">{formatTime(item.started_at)}</span><ArrowRight className="size-4 text-[#5a9269]" /></Link>)}</div>}
  </div>;
}
