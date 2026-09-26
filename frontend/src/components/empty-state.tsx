import Link from "next/link";
import { ArrowUpRight, ClipboardList } from "lucide-react";

export function EmptyState({ title, description, action = true }: { title: string; description: string; action?: boolean }) {
  return <div className="rounded-2xl border border-dashed border-[#ccdcd1] bg-white px-6 py-16 text-center">
    <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-[#e6f3e9] text-[#27714f]"><ClipboardList className="size-6" /></div>
    <h2 className="text-lg font-semibold text-[#1c3b30]">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#74897c]">{description}</p>
    {action && <Link href="/cases/new" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#1f6849] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#175139]">Open a case <ArrowUpRight className="size-4" /></Link>}
  </div>;
}
