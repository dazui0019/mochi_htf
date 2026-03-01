from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


StepType = Literal["Action", "Verify"]


class TestStep(BaseModel):
    id: str
    name: str
    type: StepType
    plugin: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    expr: str | None = None
    timeout: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_expr(self) -> "TestStep":
        if self.type == "Verify" and not self.expr:
            raise ValueError("Verify step requires expr")
        return self


class TestItem(BaseModel):
    id: str
    name: str
    steps: list[TestStep]


class TestCase(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    items: list[TestItem]


class RunStartRequest(BaseModel):
    case_id: str
