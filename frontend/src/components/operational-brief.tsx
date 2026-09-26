import { ArrowRight, Check, CircleHelp, MapPin, ShieldCheck, TriangleAlert } from "lucide-react";
import type { Brief } from "@/lib/types";

function section(label: string, text: string | null | undefined, icon: React.ReactNode) {
  return <div className="flex gap-3.5 border-b border-[#e6ede7] py-5 last:border-0"><span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-[#edf5ed] text-[#3d805b]">{icon}</span><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#628b72]">{label}</p><p className="mt-1.5 text-sm leading-6 text-[#2c4839]">{text || "Waiting for investigation results"}</p></div></div>;
}

export function OperationalBrief({ brief }: { brief: Brief }) {
  const where = brief.where;
  const why = brief.why;
  const action = brief.proposed_action;
  const validation = brief.validation;
  const whyText = why.constraint ? [typeof why.delay_minutes === "number" ? `${why.delay_minutes}-minute delay.` : null, why.constraint.reason || "Crew duty constraint identified."].filter(Boolean).join(" ") : typeof why.delay_minutes === "number" ? `${why.delay_minutes}-minute flight delay recorded. Duty investigation is in progress.` : null;
  const checks = [
    { label: "Reserve found", value: validation.reserve_found },
    { label: "Candidate validated", value: validation.candidate_valid },
    { label: "Simulation passed", value: validation.simulation_safe },
  ];
  return <section className="overflow-hidden rounded-2xl border border-[#e1eae2] bg-white shadow-[0_8px_30px_-20px_#18382d25]">
    <div className="border-b border-[#e7eee8] px-6 py-5"><p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#678778]">Operational brief</p><h2 className="mt-1 text-lg font-semibold text-[#17382b]">Situation at a glance</h2></div>
    <div className="px-6">
      {section("Where", [where.flight_id, where.origin && where.destination ? `${where.origin} → ${where.destination}` : null, where.affected_crew_id ? `Crew ${where.affected_crew_id}` : null].filter(Boolean).join(" · ") || null, <MapPin className="size-4" />)}
      {section("Why", whyText, <CircleHelp className="size-4" />)}
      {section("So what", brief.so_what, <TriangleAlert className="size-4" />)}
      <div className="border-b border-[#e6ede7] py-5"><div className="flex items-start gap-3.5"><span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-[#edf5ed] text-[#3d805b]"><ArrowRight className="size-4" /></span><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#628b72]">Proposed action</p><p className="mt-1.5 text-sm font-semibold text-[#2c4839]">{action.remove_crew_id && action.replacement_crew_id ? <>{action.remove_crew_id} <ArrowRight className="mx-1 inline size-4" /> {action.replacement_crew_id}</> : "Pending candidate search"}</p>{action.candidate_name && <p className="mt-1 text-xs text-[#81948a]">Replacement: {action.candidate_name}</p>}</div></div></div>
      <div className="py-5"><div className="mb-3 flex items-center gap-3.5"><span className="flex size-8 items-center justify-center rounded-lg bg-[#edf5ed] text-[#3d805b]"><ShieldCheck className="size-4" /></span><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#628b72]">Validation</p></div><div className="ml-[46px] space-y-2.5">{checks.map((item) => <div key={item.label} className={`flex items-center gap-2 text-xs ${item.value === true ? "text-[#257b4d]" : item.value === false ? "text-[#a64f42]" : "text-[#9cad9e]"}`}><span className={`flex size-4 items-center justify-center rounded-full ${item.value === true ? "bg-[#daf3e2]" : item.value === false ? "bg-[#fceae5]" : "bg-[#edf1ed]"}`}>{item.value === true ? <Check className="size-3" /> : item.value === false ? "×" : "·"}</span>{item.label}</div>)}</div></div>
    </div>
  </section>;
}
