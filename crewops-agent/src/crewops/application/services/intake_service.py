"""Select a supported human-written runbook from an operator's case description."""

import re
from dataclasses import dataclass


FLIGHT_ID = re.compile(r"\bFL-\d{1,6}\b", re.IGNORECASE)
DUTY_RISK = re.compile(r"\b(?:delay(?:ed)?|late|duty|duty.clock|duty.time|hours.limit)\b", re.IGNORECASE)


@dataclass(frozen=True)
class IntakeDecision:
    issue: str
    flight_id: str
    runbook_id: str
    selection_reason: str


class IncidentIntakeService:
    """Explicitly match only the operational scenario this MVP can execute."""

    def __init__(self, supported_runbook_id: str) -> None:
        self.supported_runbook_id = supported_runbook_id

    def select(self, issue: str) -> IntakeDecision:
        if not isinstance(issue, str) or not issue.strip():
            raise ValueError("Describe the operational issue")
        text = issue.strip()
        if len(text) > 1000:
            raise ValueError("Issue description must be 1000 characters or fewer")
        flight = FLIGHT_ID.search(text)
        if flight is None:
            raise ValueError("Include a flight ID such as FL-1042")
        if DUTY_RISK.search(text) is None:
            raise ValueError("This MVP supports delayed-flight or crew duty-risk cases. Describe the delay or duty concern.")
        return IntakeDecision(
            issue=text,
            flight_id=flight.group().upper(),
            runbook_id=self.supported_runbook_id,
            selection_reason="Flight-linked delay or duty concern matched the supported crew duty risk procedure.",
        )
