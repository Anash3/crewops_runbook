"""CrewOps SQL and mock action adapters registered as MCP tools."""

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import bindparam, text


class CrewOpsDatabaseTools:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def flight_get(self, flight_id: str) -> dict[str, Any]:
        """Get the scheduled details and current status of a flight by flight ID."""
        query = text(
            """SELECT flight_id, origin, destination, scheduled_time, status,
                      delay_minutes
               FROM flight
               WHERE flight_id = :flight_id"""
        )
        with self._connect() as conn:
            row = conn.execute(query, {"flight_id": flight_id}).mappings().fetchone()
        if row is None:
            raise ValueError(f"Flight {flight_id} was not found")
        return dict(row)


    def flight_roster(self, flight_id: str) -> list[dict[str, Any]]:
        """List the crew assigned to a flight."""
        query = text(
            """SELECT c.crew_id, c.name, c.rank
               FROM flight_roster fr
               JOIN flight f ON fr.flight_id = f.id
               JOIN crew c ON fr.crew_id = c.id
               WHERE f.flight_id = :flight_id
               ORDER BY c.crew_id"""
        )
        with self._connect() as conn:
            rows = conn.execute(query, {"flight_id": flight_id}).mappings().fetchall()
        return [dict(row) for row in rows]


    def duty_clock_get(self, crew_ids: list[str]) -> list[dict[str, Any]]:
        """Get duty totals and limits for the listed assigned crew members."""
        if not crew_ids:
            return []
        query = text(
            """SELECT c.crew_id, dc.total_minutes, dc.max_allowed
               FROM duty_clock dc
               JOIN crew c ON dc.crew_id = c.id
               WHERE c.crew_id IN :crew_ids
               ORDER BY c.crew_id"""
        ).bindparams(bindparam("crew_ids", expanding=True))
        with self._connect() as conn:
            rows = conn.execute(query, {"crew_ids": crew_ids}).mappings().fetchall()
        found = {row["crew_id"] for row in rows}
        missing = sorted(set(crew_ids) - found)
        if missing:
            raise ValueError(f"Duty clock was not found for crew: {', '.join(missing)}")
        return [dict(row) for row in rows]


    def reserve_search(
        self,
        base: str, rank: str, exclude_crew_ids: list[str]
    ) -> dict[str, Any]:
        """Find available reserves at the flight origin with the required rank."""
        query = text(
            """SELECT c.crew_id, c.name, c.rank, c.base
               FROM reserve r
               JOIN crew c ON c.id = r.crew_id
               WHERE r.available IS TRUE
                 AND c.base = :base
                 AND c.rank = :rank
                 AND c.crew_id NOT IN :exclude_crew_ids
               ORDER BY c.crew_id"""
        ).bindparams(bindparam("exclude_crew_ids", expanding=True))
        with self._connect() as conn:
            rows = conn.execute(
                query,
                {
                    "base": base,
                    "rank": rank,
                    "exclude_crew_ids": exclude_crew_ids or [""],
                },
            ).mappings().fetchall()
        candidates = [dict(row) for row in rows]
        return {
            "base": base,
            "required_rank": rank,
            "candidates": candidates,
            "candidate_count": len(candidates),
        }


    def _candidate_validation(
        self,
        conn: Any, flight_id: str, candidate_id: str, required_rank: str, delay_minutes: int
    ) -> dict[str, Any]:
        query = text(
            """SELECT c.crew_id, c.name, c.rank, c.base, f.origin AS flight_origin,
                      COALESCE(r.available, FALSE) AS reserve_available,
                      dc.total_minutes, dc.max_allowed, cert.expires_at
               FROM crew c
               JOIN flight f ON f.flight_id = :flight_id
               LEFT JOIN reserve r ON r.crew_id = c.id
               LEFT JOIN duty_clock dc ON dc.crew_id = c.id
               LEFT JOIN certification cert ON cert.crew_id = c.id
               WHERE c.crew_id = :candidate_id"""
        )
        row = conn.execute(
            query, {"flight_id": flight_id, "candidate_id": candidate_id}
        ).mappings().fetchone()
        if row is None:
            return {
                "candidate_id": candidate_id,
                "valid": False,
                "issues": ["Candidate or flight was not found."],
            }

        candidate = dict(row)
        issues: list[str] = []
        if not candidate["reserve_available"]:
            issues.append("Candidate is not marked as an available reserve.")
        if candidate["rank"] != required_rank:
            issues.append("Candidate rank does not match the constrained position.")
        if candidate["base"] != candidate["flight_origin"]:
            issues.append("Candidate is not based at the flight origin.")
        if candidate["total_minutes"] is None or candidate["max_allowed"] is None:
            issues.append("Candidate duty clock is missing.")
        else:
            projected = int(candidate["total_minutes"]) + max(0, int(delay_minutes))
            candidate["projected_duty_minutes"] = projected
            if projected > int(candidate["max_allowed"]):
                issues.append("Candidate would exceed the duty limit after delay exposure.")
        expiry = candidate["expires_at"]
        if expiry is None or expiry < date.today():
            issues.append("Candidate certification is missing or expired.")
        candidate["certification_valid"] = expiry is not None and expiry >= date.today()
        candidate["duty_limit_passed"] = (
            candidate.get("projected_duty_minutes") is not None
            and candidate.get("max_allowed") is not None
            and candidate["projected_duty_minutes"] <= candidate["max_allowed"]
        )
        candidate["checks"] = {
            "availability": bool(candidate["reserve_available"]),
            "qualification": candidate["rank"] == required_rank,
            "base_match": candidate["base"] == candidate["flight_origin"],
            "duty_limit": candidate["duty_limit_passed"],
            "certification": candidate["certification_valid"],
        }
        candidate["valid"] = not issues
        candidate["issues"] = issues
        return candidate


    def validate_candidate(
        self,
        flight_id: str,
        candidate_id: str,
        required_rank: str,
        delay_minutes: int,
    ) -> dict[str, Any]:
        """Validate reserve availability, position, base, duty, and certification."""
        with self._connect() as conn:
            return self._candidate_validation(
                conn, flight_id, candidate_id, required_rank, delay_minutes
            )


    def simulate_roster_change(
        self,
        flight_id: str,
        crew_to_remove: str,
        replacement_crew_id: str,
        required_rank: str,
        delay_minutes: int,
    ) -> dict[str, Any]:
        """Check the proposed substitution against current roster and candidate data."""
        roster_query = text(
            """SELECT c.crew_id, c.name, c.rank
               FROM flight_roster fr
               JOIN flight f ON f.id = fr.flight_id
               JOIN crew c ON c.id = fr.crew_id
               WHERE f.flight_id = :flight_id
               ORDER BY c.crew_id"""
        )
        with self._connect() as conn:
            roster = [
                dict(row)
                for row in conn.execute(
                    roster_query, {"flight_id": flight_id}
                ).mappings().fetchall()
            ]
            validation = self._candidate_validation(
                conn, flight_id, replacement_crew_id, required_rank, delay_minutes
            )

        current_ids = {member["crew_id"] for member in roster}
        current_member = next(
            (member for member in roster if member["crew_id"] == crew_to_remove), None
        )
        issues = list(validation.get("issues", []))
        if current_member is None:
            issues.append("The crew member selected for replacement is not on the flight roster.")
        elif current_member["rank"] != required_rank:
            issues.append("The constrained position does not match the selected crew member.")
        if replacement_crew_id in current_ids:
            issues.append("The reserve candidate is already on the flight roster.")

        checks = {
            **validation.get("checks", {}),
            "removed_crew_on_roster": current_member is not None,
            "removed_position_rank_matches": bool(
                current_member is not None and current_member["rank"] == required_rank
            ),
            "replacement_not_already_assigned": replacement_crew_id not in current_ids,
        }

        return {
            "flight_id": flight_id,
            "safe": not issues,
            "read_only": True,
            "issues": issues,
            "current_roster": roster,
            "proposed_removal": crew_to_remove,
            "proposed_replacement": replacement_crew_id,
            "required_rank": required_rank,
            "candidate_validation": validation,
            "checks": checks,
            "message": (
                "Substitution passed read-only sandbox checks."
                if not issues
                else "Substitution failed sandbox checks."
            ),
        }


    def roster_apply_change(
        self,
        flight_id: str, crew_to_remove: str, replacement_crew_id: str
    ) -> dict[str, Any]:
        """Mock the destructive roster operation; it deliberately changes no data."""
        return {
            "flight_id": flight_id,
            "crew_to_remove": crew_to_remove,
            "replacement_crew_id": replacement_crew_id,
            "mock": True,
            "mutated": False,
            "message": "Mock roster action only; no roster data was changed.",
        }


    def verify_roster(
        self,
        flight_id: str,
        original_crew_ids: list[str],
        crew_to_remove: str,
        replacement_crew_id: str,
        apply_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify the expected roster state after a real or mock action."""
        actual_roster = self.flight_roster(flight_id)
        actual_ids = {member["crew_id"] for member in actual_roster}
        if apply_result.get("mutated"):
            expected_ids = (set(original_crew_ids) - {crew_to_remove}) | {
                replacement_crew_id
            }
        else:
            expected_ids = set(original_crew_ids)
        verified = actual_ids == expected_ids
        return {
            "flight_id": flight_id,
            "verified": verified,
            "status": (
                "VERIFIED_CHANGE"
                if verified and apply_result.get("mutated")
                else "MOCK_NO_MUTATION_CONFIRMED"
                if verified and apply_result.get("mock")
                else "VERIFICATION_FAILED"
            ),
            "actual_crew_ids": sorted(actual_ids),
            "expected_crew_ids": sorted(expected_ids),
            "mock": bool(apply_result.get("mock")),
            "mutated": bool(apply_result.get("mutated")),
        }
