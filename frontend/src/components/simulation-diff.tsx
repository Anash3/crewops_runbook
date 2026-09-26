import { ArrowRightLeft, Check, FlaskConical } from "lucide-react";
import type { Simulation } from "@/lib/types";

export function SimulationDiff({ simulation }: { simulation: Simulation }) {
  if (!simulation.available) return null;
  const removed = simulation.remove_crew_id;
  const added = simulation.replacement_crew_id;
  return <section className="overflow-hidden rounded-2xl border border-[#dce9e0] bg-white">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#e6eee8] px-6 py-5"><div><p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#678778]">Roster preview</p><h2 className="mt-1 flex items-center gap-2 text-lg font-semibold text-[#17382b]"><ArrowRightLeft className="size-5 text-[#4c956a]" /> Roster change</h2></div><span className="inline-flex items-center gap-1.5 rounded-full border border-[#bddfc9] bg-[#eff8f1] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#357957]"><FlaskConical className="size-3.5" /> Simulated · not applied</span></div>
    <div className="grid gap-0 sm:grid-cols-2"><div className="border-b border-[#e6eee8] p-6 sm:border-r sm:border-b-0"><p className="mb-4 text-[10px] font-bold uppercase tracking-[0.17em] text-[#8aa092]">Current roster</p><div className="space-y-2">{simulation.current_roster.map((id) => <div key={id} className={`rounded-lg border px-3 py-2.5 font-mono text-sm ${id === removed ? "border-rose-200 bg-rose-50 text-rose-700 line-through" : "border-[#e7eee8] bg-[#fafcf9] text-[#455f4d]"}`}>{id === removed ? "− " : "  "}{id}</div>)}</div></div><div className="p-6"><p className="mb-4 text-[10px] font-bold uppercase tracking-[0.17em] text-[#8aa092]">Proposed roster</p><div className="space-y-2">{simulation.proposed_roster.map((id) => <div key={id} className={`rounded-lg border px-3 py-2.5 font-mono text-sm ${id === added ? "border-emerald-200 bg-emerald-50 font-semibold text-emerald-700" : "border-[#e7eee8] bg-[#fafcf9] text-[#455f4d]"}`}>{id === added ? "+ " : "  "}{id}</div>)}</div></div></div>
    <div className={`flex items-center gap-2 border-t px-6 py-3 text-xs font-medium ${simulation.safe ? "border-[#dce9e0] bg-[#f4faf5] text-[#367654]" : "border-rose-200 bg-rose-50 text-rose-700"}`}>{simulation.safe ? <Check className="size-4" /> : "!"}{simulation.safe ? "Simulation passed. Production roster is unchanged." : simulation.issues.join(" · ") || "Simulation did not pass."}</div>
  </section>;
}
