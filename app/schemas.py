"""Pydantic request models for endpoint validation."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ReportBody(BaseModel):
    report_type: Literal["lost", "found"]
    title: str = Field(min_length=4, max_length=100)
    description: str = Field(min_length=10, max_length=1200)
    category: str
    # Optional public characteristics improve search/matching; never put secret proof here.
    brand: str | None = Field(default=None, max_length=80)
    primary_color: str | None = Field(default=None, max_length=60)
    visible_features: str | None = Field(default=None, max_length=400)
    occurred_at: str | None = None
    location_block: str | None = Field(default=None, max_length=80)
    location_floor: str | None = Field(default=None, max_length=40)
    location_room: str | None = Field(default=None, max_length=80)
    location_area: str | None = Field(default=None, max_length=120)


class ReportCloseBody(BaseModel):
    reason: Literal["recovered_elsewhere", "no_longer_searching", "duplicate", "found_report_withdrawn"]
    note: str | None = Field(default=None, max_length=400)


class ClaimDisputeBody(BaseModel):
    reason: str = Field(min_length=20, max_length=1000)


class IntakeBody(BaseModel):
    confirmed_physical_receipt: bool
    storage_location: str = Field(min_length=4, max_length=160)
    private_detail: str | None = Field(default=None, max_length=1200)
    value_band: Literal["low", "medium", "high", "unknown"] = "unknown"
    sensitivity_level: int = Field(default=1, ge=1, le=4)


class StorageLocationBody(BaseModel):
    storage_location: str = Field(min_length=4, max_length=160)
    note: str | None = Field(default=None, max_length=800)


class ClaimBody(BaseModel):
    report_id: str
    evidence: str = Field(min_length=20, max_length=1800)
    lost_report_id: str | None = None
    evidence_types: list[str] = Field(min_length=1, max_length=6)


class ClaimEvidenceBody(BaseModel):
    evidence: str = Field(min_length=20, max_length=1800)


class ClaimDecisionBody(BaseModel):
    action: Literal["approve", "reject", "request_more_evidence", "mark_disputed"]
    note: str | None = Field(default=None, max_length=800)
    verification_checks: list[str] = Field(default_factory=list)


class HandoverBody(BaseModel):
    confirmed_physical_handover: bool
    claimant_identity_checked: bool
    tag_id: str = Field(min_length=4, max_length=80)
    note: str | None = Field(default=None, max_length=800)
