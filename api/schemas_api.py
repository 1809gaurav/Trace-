"""Typed HTTP request and response schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class APIErrorSchema(BaseModel):
    """Stable public error envelope."""

    code: str
    message: str
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    """Top-level error body."""

    error: APIErrorSchema


class CaseCreateRequest(BaseModel):
    """Create-case request."""

    title: str = Field(default="Untitled case", min_length=1, max_length=240)


class GroundTruthRequest(BaseModel):
    """Synthetic benchmark ground truth."""

    ground_truth: dict[str, Any]


class TamperDemoRequest(BaseModel):
    """Request to alter an in-memory custody copy."""

    index: int = Field(ge=1)


class CaseResponse(BaseModel):
    """Case summary."""

    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class RunResponse(BaseModel):
    """Recovery run status."""

    id: str
    case_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
    engine_mode: Literal["fake", "real"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    integrity_ok: bool | None = None
    error_message: str | None = None
