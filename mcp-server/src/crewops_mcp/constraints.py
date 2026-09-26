"""Pure duty constraint interpretation for the CrewOps scenario."""

from typing import Any


def identify_constraint(
    delay_minutes: int,
    roster: list[dict[str, Any]],
    duty_clocks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare delayed-operation duty exposure with each assigned crew limit."""
    roster_by_id = {item["crew_id"]: item for item in roster}
    constraints = []
    for clock in duty_clocks:
        crew_id = clock["crew_id"]
        projected = int(clock["total_minutes"]) + max(0, int(delay_minutes))
        limit = int(clock["max_allowed"])
        if projected > limit:
            crew = roster_by_id.get(crew_id, {})
            constraints.append(
                {
                    "crew_id": crew_id,
                    "name": crew.get("name"),
                    "required_rank": crew.get("rank"),
                    "current_duty_minutes": int(clock["total_minutes"]),
                    "delay_exposure_minutes": max(0, int(delay_minutes)),
                    "projected_duty_minutes": projected,
                    "max_allowed_minutes": limit,
                    "over_limit_minutes": projected - limit,
                    "reason": "Projected duty exceeds the recorded maximum.",
                }
            )
    return {
        "has_constraint": bool(constraints),
        # This scenario handles one constrained position. If several crew are
        # over limit, stop before proposing a partial crew substitution.
        "replacement_supported": len(constraints) == 1,
        "constraints": constraints,
        "rule": "current duty minutes + flight delay minutes > maximum allowed minutes",
    }
