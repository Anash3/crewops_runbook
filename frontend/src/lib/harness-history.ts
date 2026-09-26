export type RecentHarnessCase = {
  case_id: string;
  flight_id: string | null;
  started_at: string | null;
};

const historyKey = "crewops:recent-harness-cases";
const lastCaseKey = "crewops:last-case-id";
const validCaseId = (value: unknown): value is string =>
  typeof value === "string" && /^[a-f0-9]{32}$/.test(value);

export function recentHarnessCases(): RecentHarnessCase[] {
  try {
    const saved = JSON.parse(window.localStorage.getItem(historyKey) || "[]");
    const cases: RecentHarnessCase[] = Array.isArray(saved)
      ? saved.filter((item): item is RecentHarnessCase =>
          item && validCaseId(item.case_id))
      : [];
    const lastCaseId = window.localStorage.getItem(lastCaseKey);
    if (validCaseId(lastCaseId) && !cases.some((item) => item.case_id === lastCaseId)) {
      cases.unshift({ case_id: lastCaseId, flight_id: null, started_at: null });
    }
    return cases.slice(0, 10);
  } catch {
    return [];
  }
}

export function rememberHarnessCase(caseId: string, flightId?: string): void {
  if (!validCaseId(caseId)) return;
  const existing = recentHarnessCases();
  const previous = existing.find((item) => item.case_id === caseId);
  const current: RecentHarnessCase = {
    case_id: caseId,
    flight_id: flightId || previous?.flight_id || null,
    started_at: previous?.started_at || new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(lastCaseKey, caseId);
    window.localStorage.setItem(historyKey, JSON.stringify([
      current,
      ...existing.filter((item) => item.case_id !== caseId),
    ].slice(0, 10)));
  } catch {
    // Browser storage can be disabled; the case URL remains usable.
  }
}
