export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  return readResponse<T>(response);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readResponse<T>(response);
}

async function readResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return payload as T;
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function stepLabel(id: string): string {
  const names: Record<string, string> = {
    get_flight: "Get flight",
    get_roster: "Get roster",
    check_duty_clock: "Check duty clock",
    identify_constraint: "Identify constraint",
    search_reserve: "Search reserve",
    validate_candidate: "Validate candidate",
    simulate_change: "Simulate change",
    apply_change: "Apply change",
    verify: "Verify roster",
  };
  return names[id] || id.replaceAll("_", " ");
}
