export type RunStatus =
  | "RUNNING"
  | "WAITING_FOR_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "COMPLETED"
  | "FAILED"
  | "BLOCKED";

export type RunSummary = {
  run_id: string;
  case_id?: string | null;
  runbook_id: string;
  runbook_name: string;
  runbook_version: string;
  flight_id: string;
  issue: string | null;
  status: RunStatus;
  started_at: string | null;
  updated_at: string | null;
  completed_steps: number;
  total_steps: number;
};

export type RunStep = {
  id: string;
  description: string;
  tool: string;
  destructive: boolean;
  mock?: boolean;
  status: string;
  arguments: Record<string, unknown> | null;
  result: unknown;
  reason: string | null;
  observation: string | null;
  next_decision: string | null;
};

export type TraceEntry = {
  id: number;
  type: "ROUTE" | "PLAN" | "THINK" | "ACT" | "OBSERVE" | "GATE" | "APPROVAL" | "ERROR" | "SKIP" | "DONE";
  step_id: string | null;
  timestamp: string | null;
  message: string | null;
  tool: string | null;
  arguments: Record<string, unknown> | null;
  checks: Array<{ key: string; label: string; passed: boolean; detail: string | null }> | null;
};

export type Approval = {
  approval_id: string;
  action_hash: string;
  expires_at: string;
  run_id: string;
  runbook_id: string;
  step_id: string;
  tool: string;
  arguments: {
    flight_id?: string;
    crew_to_remove?: string;
    replacement_crew_id?: string;
    [key: string]: unknown;
  };
  proposal: {
    flight_id?: string;
    delay_minutes?: number;
    remove_crew_id?: string;
    replacement_crew_id?: string;
    candidate_name?: string;
    simulation?: { safe?: boolean; read_only?: boolean; issues?: string[] };
    simulation_checks?: Record<string, boolean>;
    mock_action?: boolean;
    production_state_modified?: boolean;
  };
};

export type Brief = {
  where: {
    flight_id?: string;
    origin?: string;
    destination?: string;
    affected_crew_id?: string;
    affected_crew_name?: string;
  };
  why: {
    delay_minutes?: number;
    constraint?: {
      crew_id?: string;
      projected_duty_minutes?: number;
      max_allowed_minutes?: number;
      over_limit_minutes?: number;
      reason?: string;
    } | null;
    rule?: string;
  };
  so_what?: string | null;
  proposed_action: {
    remove_crew_id?: string;
    replacement_crew_id?: string;
    candidate_name?: string;
  };
  validation: {
    reserve_found: boolean | null;
    candidate_valid?: boolean | null;
    checks: Record<string, boolean>;
    simulation_safe?: boolean | null;
    simulation_checks: Record<string, boolean>;
  };
};

export type Simulation = {
  available: boolean;
  safe?: boolean | null;
  read_only?: boolean | null;
  issues: string[];
  current_roster: string[];
  proposed_roster: string[];
  remove_crew_id?: string;
  replacement_crew_id?: string;
};

export type RunDetail = RunSummary & {
  description: string;
  selection_reason: string | null;
  current_step: string | null;
  steps: RunStep[];
  brief: Brief;
  simulation: Simulation;
  approval: Approval | null;
  approval_status: string;
  action: { mock?: boolean; mutated?: boolean } | null;
  verification: {
    verified?: boolean;
    status?: string;
    actual_crew_ids?: string[];
    expected_crew_ids?: string[];
    mock?: boolean;
    mutated?: boolean;
  } | null;
  report: { status?: string } | null;
  failure: { step_id?: string; reason?: string } | null;
  events_count: number;
  trace: TraceEntry[];
};

export type Runbook = {
  id: string;
  name: string;
  version: string;
  description: string;
  steps: Array<{
    id: string;
    description: string;
    tool: string;
    destructive: boolean;
    timeout: number;
  }>;
};

export type Overview = {
  active_runs: number;
  awaiting_approval: number;
  completed_today: number;
  recent_runs: RunSummary[];
};
