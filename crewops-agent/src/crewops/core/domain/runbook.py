"""Human-authored runbook schema."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunbookStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    when: str | None = None
    destructive: bool
    mock: bool = False
    timeout: float = Field(default=30.0, gt=0)


class Runbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(default="1.0", min_length=1)
    description: str = Field(min_length=1)
    steps: list[RunbookStep] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_step_ids(self) -> "Runbook":
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Runbook step IDs must be unique")
        return self
