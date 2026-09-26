"""Public, evidence-based summaries for the runbook's observable decisions.

These are operator-facing explanations of deterministic runbook execution, not
private model chain of thought or claims that an LLM made a tool decision.
"""

from typing import Any

from crewops.core.domain.runbook import RunbookStep


CHECK_LABELS = {
    "availability": "Reserve available",
    "qualification": "Required rank",
    "base_match": "At flight origin",
    "duty_limit": "Within duty limit",
    "certification": "Certification current",
    "removed_crew_on_roster": "Crew to remove is assigned",
    "removed_position_rank_matches": "Removed crew rank matches",
    "replacement_not_already_assigned": "Replacement is not already assigned",
}


def check_details(step_id: str, result: Any) -> list[dict[str, Any]]:
    """Explain each validation result with values returned by CrewOps."""
    if step_id not in {"validate_candidate", "simulate_change"} or not isinstance(result, dict):
        return []
    checks = result.get("checks") or {}
    candidate = result if step_id == "validate_candidate" else result.get("candidate_validation") or {}
    details = []
    for key, passed in checks.items():
        if not isinstance(passed, bool):
            continue
        explanation = None
        if key == "availability":
            explanation = "Reserve is marked available" if passed else "Reserve is unavailable"
        elif key == "qualification" and candidate.get("rank"):
            explanation = f"Crew rank: {candidate['rank']}"
        elif key == "base_match" and candidate.get("base") and candidate.get("flight_origin"):
            explanation = f"Base {candidate['base']}; flight origin {candidate['flight_origin']}"
        elif key == "duty_limit" and candidate.get("projected_duty_minutes") is not None and candidate.get("max_allowed") is not None:
            explanation = f"Projected {candidate['projected_duty_minutes']} min; limit {candidate['max_allowed']} min"
        elif key == "certification" and candidate.get("expires_at"):
            explanation = f"Expires {candidate['expires_at']}"
        elif key == "removed_crew_on_roster":
            explanation = f"Crew {result.get('proposed_removal')} {'found on roster' if passed else 'missing from roster'}"
        elif key == "removed_position_rank_matches" and result.get("required_rank"):
            explanation = f"Required rank: {result['required_rank']}"
        elif key == "replacement_not_already_assigned":
            explanation = f"Crew {result.get('proposed_replacement')} {'is not on the roster' if passed else 'is already assigned'}"
        details.append({
            "key": key,
            "label": CHECK_LABELS.get(key, key.replace("_", " ").capitalize()),
            "passed": passed,
            "detail": explanation,
        })
    if step_id == "simulate_change" and isinstance(result.get("read_only"), bool):
        details.append({
            "key": "read_only",
            "label": "Read-only simulation",
            "passed": result["read_only"],
            "detail": "No roster write was requested by the simulation tool" if result["read_only"] else "Simulation did not report read-only mode",
        })
    return details


def checks_sentence(step_id: str, result: Any) -> str:
    checks = check_details(step_id, result)
    return "; ".join(f"{item['label']} {'passed' if item['passed'] else 'failed'}" for item in checks)


def plan_for_step(step: RunbookStep, context: dict[str, Any], approved: bool = False) -> str:
    flight = context.get("get_flight") or {}
    roster = context.get("get_roster") or []
    constraints = (context.get("identify_constraint") or {}).get("constraints") or []
    constraint = constraints[0] if len(constraints) == 1 else {}
    candidates = (context.get("search_reserve") or {}).get("candidates") or []
    candidate = context.get("validate_candidate") or (candidates[0] if candidates else {})
    delay = flight.get("delay_minutes")
    flight_id = flight.get("flight_id", context.get("flight_id", "the flight"))
    if step.destructive:
        return (
            f"Human approval is recorded for the exact {constraint.get('crew_id')} → {candidate.get('crew_id')} action on {flight_id}. I can call the approved tool now."
            if approved else
            f"The read-only simulation passed for {constraint.get('crew_id')} → {candidate.get('crew_id')}. The roster tool is a destructive boundary, so I must stop for human approval."
        )
    plans = {
        "get_flight": f"First I need the recorded route and delay for {flight_id} to establish the incident.",
        "get_roster": f"{flight_id} has a recorded {delay}-minute delay. I need its assigned crew to assess duty exposure.",
        "check_duty_clock": f"The roster contains {len(roster)} crew member(s). I need their duty totals and limits.",
        "identify_constraint": f"I have duty clocks and a {delay}-minute delay. I can compare projected duty against each recorded limit.",
        "search_reserve": f"{constraint.get('crew_id')} is over the recorded duty limit. I need an available reserve with the matching rank at {flight.get('origin')}.",
        "validate_candidate": f"Reserve {candidate.get('crew_id')} was found. I need to check availability, rank, base, duty capacity, and certification.",
        "simulate_change": f"Candidate {candidate.get('crew_id')} validation: {checks_sentence('validate_candidate', candidate)}. I need a read-only substitution check before approval.",
        "verify": f"The approved action returned for {flight_id}. I need to read the roster again and confirm {'the stored assignments stayed unchanged after the preview' if (context.get('apply_change') or {}).get('mock') else 'the expected change'}.",
    }
    return plans.get(step.id, step.description)


def observe_and_decide(step_id: str, result: Any) -> tuple[str | None, str | None]:
    if result is None:
        return None, None
    value = result if isinstance(result, dict) else {}
    if step_id == "get_flight" and value:
        delay = value.get("delay_minutes")
        route = f" from {value['origin']} to {value['destination']}" if value.get("origin") and value.get("destination") else ""
        observation = f"{value.get('flight_id')}{route} has a {delay}-minute recorded delay." if delay is not None else f"Flight {value.get('flight_id')}{route} was found."
        return observation, "Inspect assigned crew to assess duty exposure."
    if step_id == "get_roster" and isinstance(result, list):
        ids = ", ".join(str(item.get("crew_id")) for item in result if isinstance(item, dict))
        return f"{len(result)} assigned crew: {ids}.", "Read duty clocks for the assigned crew."
    if step_id == "check_duty_clock" and isinstance(result, list):
        clocks = "; ".join(f"{item.get('crew_id')}: {item.get('total_minutes')}/{item.get('max_allowed')} minutes" for item in result if isinstance(item, dict))
        return f"Duty clocks: {clocks}.", "Compare each total plus the delay against its limit."
    if step_id == "identify_constraint" and value:
        constraints = value.get("constraints") or []
        if len(constraints) == 1:
            item = constraints[0]
            return f"{item.get('crew_id')}: {item.get('current_duty_minutes')} duty minutes + {item.get('delay_exposure_minutes')} delay minutes = {item.get('projected_duty_minutes')} projected minutes; limit {item.get('max_allowed_minutes')} minutes, over by {item.get('over_limit_minutes')} minutes.", "One constrained position is supported; search for a matching reserve."
        return f"{len(constraints)} duty constraint(s) identified.", "Continue only if the runbook supports this constraint count."
    if step_id == "search_reserve" and value:
        candidates = value.get("candidates") or []
        ids = ", ".join(str(item.get("crew_id")) for item in candidates if isinstance(item, dict))
        return f"{len(candidates)} available reserve(s) at {value.get('base')} with rank {value.get('required_rank')}{': ' + ids if ids else ''}.", "Validate the selected candidate's availability, qualification, duty, and certification."
    if step_id == "validate_candidate" and value:
        return f"CrewOps completed validation for candidate {value.get('crew_id', value.get('candidate_id'))}. Review each returned check below.", "Simulate the exact substitution." if value.get("valid") is True else "Stop: candidate validation failed."
    if step_id == "simulate_change" and value:
        return f"CrewOps completed a read-only simulation for {value.get('proposed_removal')} → {value.get('proposed_replacement')}. Review each returned check below.", "Request human approval for the exact action." if value.get("safe") is True else "Stop before approval; simulation found a conflict."
    if step_id == "apply_change" and value:
        if value.get("mock") is True and value.get("mutated") is False:
            return "The approved preview completed. No stored roster assignment was changed.", "Read the roster again to confirm it stayed unchanged."
        if value.get("mutated") is True:
            return "The approved roster change was applied.", "Read the roster again to verify the replacement."
        return "The roster action returned without a confirmed change.", "Check the final roster before closing the run."
    if step_id == "verify" and value:
        if value.get("verified") is True and value.get("mock") is True and value.get("mutated") is False:
            return "CrewOps confirmed the original crew roster is still in place after the preview.", "Close the run as a verified scenario preview."
        if value.get("verified") is True:
            return "CrewOps confirmed the final roster matches the approved replacement.", "Close the run with the verified outcome."
        return "The final roster did not match the expected state.", "Stop: final roster verification failed."
    return None, None
