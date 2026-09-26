"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, ShieldAlert } from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { apiGet, stepLabel } from "@/lib/api";
import type { Runbook } from "@/lib/types";

export default function RunbookDetailPage() {
  const { runbookId } = useParams<{ runbookId: string }>();
  const { data, isPending, error } = useQuery({ queryKey: ["runbook", runbookId], queryFn: () => apiGet<Runbook>(`/api/runbooks/${runbookId}`) });
  return <div className="max-w-5xl"><Link href="/runbooks" className="mb-5 inline-flex items-center gap-2 text-xs font-semibold text-[#56836b]"><ArrowLeft className="size-4" /> Runbooks</Link>{isPending && <div className="py-8 text-sm text-[#7e9382]">Loading definition…</div>}{error && <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error.message}</div>}{data && <><PageHeading eyebrow={`Runbook definition / v${data.version}`} title={data.name} description={data.description} /><div className="overflow-hidden rounded-2xl border border-[#e1eae2] bg-white"><div className="border-b border-[#e8eee8] px-6 py-5 text-[11px] font-bold uppercase tracking-[0.16em] text-[#75917e]">Execution sequence · {data.steps.length} steps</div><ol className="divide-y divide-[#eef2ed]">{data.steps.map((step, index) => <li key={step.id} className="flex items-start gap-4 px-6 py-5"><span className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${step.destructive ? "bg-amber-100 text-amber-800" : "bg-[#e8f4eb] text-[#4d8d61]"}`}>{String(index + 1).padStart(2, "0")}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-3"><h2 className="text-sm font-semibold text-[#2a4e36]">{stepLabel(step.id)}</h2>{step.destructive && <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-800"><ShieldAlert className="size-3" />Human approval required</span>}</div><p className="mt-1 text-xs leading-5 text-[#7f9284]">{step.description}</p><p className="mt-2 font-mono text-[11px] text-[#779382]">{step.tool} · timeout {step.timeout}s</p></div><span className="mt-1 text-[#77aa82]">{step.destructive ? <ShieldAlert className="size-4 text-amber-600" /> : <Check className="size-4" />}</span></li>)}</ol></div></>}</div>;
}
