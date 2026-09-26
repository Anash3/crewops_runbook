"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, Check, ShieldAlert } from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { apiGet } from "@/lib/api";
import type { Runbook } from "@/lib/types";

export default function RunbooksPage() {
  const { data, isPending, error } = useQuery({ queryKey: ["runbooks"], queryFn: () => apiGet<{ runbooks: Runbook[] }>("/api/runbooks") });
  return <div><PageHeading eyebrow="Human-written procedures" title="Runbooks" description="Operators define the sequence and destructive boundary. The executor follows the loaded definition." />
    {error && <div className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error.message}</div>}{isPending && <div className="rounded-2xl border bg-white p-8 text-sm text-[#819287]">Loading runbooks…</div>}
    <div className="grid gap-5 md:grid-cols-2">{data?.runbooks.map((runbook) => <Link href={`/runbooks/${runbook.id}`} key={runbook.id} className="group rounded-2xl border border-[#e1eae2] bg-white p-7 hover:border-[#a9d2b5] hover:shadow-[0_15px_35px_-26px_#2b6c42]"><div className="flex items-start justify-between"><span className="flex size-11 items-center justify-center rounded-xl bg-[#e5f4e9] text-[#3a8759]"><BookOpenText className="size-5" /></span><span className="rounded-full bg-[#f2f7f3] px-3 py-1 font-mono text-[10px] text-[#6a8c72]">v{runbook.version}</span></div><h2 className="mt-6 text-lg font-semibold text-[#1d3e2d]">{runbook.name}</h2><p className="mt-2 min-h-12 text-sm leading-6 text-[#789080]">{runbook.description}</p><div className="mt-6 flex flex-wrap gap-3 border-t border-[#e9eee9] pt-5 text-xs text-[#5b7b65]"><span className="flex items-center gap-1.5"><Check className="size-4 text-emerald-600" />{runbook.steps.length} steps</span><span className="flex items-center gap-1.5"><ShieldAlert className="size-4 text-amber-600" />{runbook.steps.filter((step) => step.destructive).length} approval gate</span></div><span className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#2e7751]">View definition <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" /></span></Link>)}</div>
  </div>;
}
