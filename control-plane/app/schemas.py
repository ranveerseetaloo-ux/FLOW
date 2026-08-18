"""Pydantic request/response schemas (API contract)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from shaper.models import PipeType  # type: ignore


class TimeWindowIn(BaseModel):
    name: str
    days: list[int] = Field(description="0=Mon .. 6=Sun")
    start: str = Field(examples=["18:00"])
    end: str = Field(examples=["23:00"])
    download_mbps: float
    upload_mbps: float


class CustomerIn(BaseModel):
    ref: str
    name: str
    contact_email: str = ""


class CustomerOut(CustomerIn):
    id: int
    active: bool
    model_config = {"from_attributes": True}


class IPGroupIn(BaseModel):
    customer_id: int
    cidr: str = Field(examples=["203.0.113.10/32", "203.0.113.0/24"])
    label: str = ""
    pipe_id: Optional[int] = None
    download_mbps: float = 0.0
    upload_mbps: float = 0.0


class IPGroupOut(IPGroupIn):
    id: int
    model_config = {"from_attributes": True}


class PipeIn(BaseModel):
    name: str
    ptype: PipeType
    download_mbps: float = 0.0
    upload_mbps: float = 0.0
    contention_ratio: int = 1
    priority: int = 3
    match_label: Optional[str] = None
    fwmark: Optional[int] = None
    windows: list[TimeWindowIn] = []


class PipeOut(BaseModel):
    id: int
    name: str
    ptype: PipeType
    download_mbps: float
    upload_mbps: float
    contention_ratio: int
    priority: int
    match_label: Optional[str] = None
    fwmark: Optional[int] = None
    model_config = {"from_attributes": True}


class CompileRequest(BaseModel):
    interface: str = "eth0"
    direction: str = "download"          # download|upload
    total_mbps: float = 1000
    apply: bool = False                  # if true and node configured, push to data plane


class CompileResponse(BaseModel):
    interface: str
    direction: str
    commands: list[str]
    warnings: list[str]
    applied: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
