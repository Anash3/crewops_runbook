import type { ReactNode } from "react";

export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
    <div><p className="mb-2 text-[11px] font-bold uppercase tracking-[0.22em] text-[#568773]">{eyebrow}</p><h1 className="text-3xl font-semibold tracking-tight text-[#18362b] md:text-[36px]">{title}</h1>{description && <p className="mt-2 max-w-2xl text-sm leading-6 text-[#6b8176]">{description}</p>}</div>
    {action}
  </div>;
}
