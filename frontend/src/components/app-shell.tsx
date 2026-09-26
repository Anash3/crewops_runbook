"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, BookOpenText, ChevronRight, ClipboardList, Cpu,
  MessageSquareText, ShieldCheck,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { Overview } from "@/lib/types";

const nav = [
  { href: "/cases/new", label: "Open case", icon: MessageSquareText },
  { href: "/harness", label: "Harness", icon: Cpu },
  { href: "/runs", label: "Case runs", icon: ClipboardList },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/runbooks", label: "Runbooks", icon: BookOpenText },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [lastCaseId, setLastCaseId] = useState<string | null>(null);
  useEffect(() => {
    const saved = window.localStorage.getItem("crewops:last-case-id");
    setLastCaseId(saved && /^[a-f0-9]{32}$/.test(saved) ? saved : null);
  }, [pathname]);
  const { isError } = useQuery({
    queryKey: ["overview", "shell"],
    queryFn: () => apiGet<Overview>("/api/overview"),
    refetchInterval: 15_000,
  });
  const current = nav.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));

  return <div className="min-h-screen bg-[#f5f7f5] text-[#18302c]">
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[238px] flex-col bg-[#142823] text-white lg:flex">
      <Link href="/cases/new" className="flex items-center gap-3 px-6 py-7">
        <span className="flex size-10 items-center justify-center rounded-xl bg-[#9ee1c3] text-[#123127]"><Activity className="size-5" strokeWidth={2.4} /></span>
        <span><span className="block text-xl font-semibold tracking-tight">CrewOps</span><span className="block text-[10px] font-medium uppercase tracking-[0.22em] text-[#9fbdb3]">On-call workspace</span></span>
      </Link>
      <div className="mx-5 h-px bg-white/10" />
      <div className="px-5 pt-7 text-[10px] font-semibold uppercase tracking-[0.22em] text-[#86a59a]">Workspace</div>
      <nav className="mt-3 space-y-1 px-3" aria-label="Main navigation">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          const destination = href === "/harness" && lastCaseId ? `/harness/${lastCaseId}` : href;
          return <Link key={href} href={destination} className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors ${active ? "bg-[#27473d] font-semibold text-white" : "text-[#bed0ca] hover:bg-white/8 hover:text-white"}`}>
            <Icon className={`size-[18px] ${active ? "text-[#a1e2c2]" : ""}`} />
            <span>{label}</span>
            {active && <ChevronRight className="ml-auto size-4 text-[#a1e2c2]" />}
          </Link>;
        })}
      </nav>
      <div className="mt-auto mx-5 mb-6 rounded-2xl border border-white/10 bg-white/5 p-4">
        <div className="flex items-center gap-2 text-xs font-medium"><span className={`size-2 rounded-full ${isError ? "bg-red-400" : "bg-emerald-400"}`} />{isError ? "Backend unavailable" : "Operational"}</div>
        <p className="mt-2 text-xs leading-5 text-[#a3bdb3]">Human approval protects every roster change.</p>
      </div>
    </aside>

    <div className="lg:pl-[238px]">
      <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-[#e3e9e5] bg-white/95 px-5 backdrop-blur md:px-9">
        <div className="flex items-center gap-3">
          <Link href="/cases/new" className="flex size-9 items-center justify-center rounded-lg bg-[#17382d] text-[#a1e2c2] lg:hidden"><Activity className="size-5" /></Link>
          <div><div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[#7d9389]">CrewOps / On-call</div><div className="text-sm font-semibold text-[#1e3a31]">{current?.label || "Operations"}</div></div>
        </div>
        <div className="hidden items-center gap-2 rounded-full border border-[#dfe8e1] px-3 py-1.5 text-xs font-medium text-[#315b48] sm:flex"><span className={`size-2 rounded-full ${isError ? "bg-red-400" : "bg-emerald-500"}`} />{isError ? "Connection unavailable" : "Operational"}</div>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b border-[#e2e9e3] bg-white px-3 py-2 lg:hidden" aria-label="Mobile navigation">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          const destination = href === "/harness" && lastCaseId ? `/harness/${lastCaseId}` : href;
          return <Link key={href} href={destination} className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium ${active ? "bg-[#e3f4e9] text-[#1a5940]" : "text-[#61776c]"}`}><Icon className="size-4" />{label}</Link>;
        })}
      </nav>
      <main className="mx-auto w-full max-w-[1500px] px-5 py-7 md:px-9 md:py-10">{children}</main>
    </div>
  </div>;
}
