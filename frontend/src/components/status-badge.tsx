import { Badge } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/types";

const labels: Record<RunStatus, string> = {
  RUNNING: "Running",
  WAITING_FOR_APPROVAL: "Awaiting approval",
  APPROVED: "Executing",
  REJECTED: "Rejected",
  COMPLETED: "Completed",
  FAILED: "Failed",
  BLOCKED: "Blocked",
};

const classes: Record<RunStatus, string> = {
  RUNNING: "border-sky-200 bg-sky-50 text-sky-800",
  WAITING_FOR_APPROVAL: "border-amber-200 bg-amber-50 text-amber-900",
  APPROVED: "border-indigo-200 bg-indigo-50 text-indigo-800",
  REJECTED: "border-zinc-200 bg-zinc-100 text-zinc-700",
  COMPLETED: "border-emerald-200 bg-emerald-50 text-emerald-800",
  FAILED: "border-red-200 bg-red-50 text-red-800",
  BLOCKED: "border-red-200 bg-red-50 text-red-800",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return <Badge variant="outline" className={`gap-2 rounded-full px-3 py-1 font-medium ${classes[status] || ""}`}>
    <span className="size-1.5 rounded-full bg-current" />{labels[status] || status}
  </Badge>;
}
