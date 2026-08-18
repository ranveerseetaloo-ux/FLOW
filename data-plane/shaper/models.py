"""
PipeCore — shared data-plane domain model.

These dataclasses are the single source of truth for what a "pipe" is.
The control plane produces them (from the database) and the tc compiler
consumes them. Keeping the model here means the compiler can be unit-tested
in isolation, with no database or API required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PipeType(str, Enum):
    """The bandwidth-package types the platform can enforce."""
    DEDICATED = "dedicated"          # 100% guarantee, no oversubscription
    CONTENDED = "contended"          # 1:N oversubscription (1:2 .. 1:20)
    TIME_BASED = "time_based"        # rate varies by time-of-day schedule
    PROTOCOL = "protocol"            # shape a matched L3/L4 protocol
    APPLICATION = "application"      # shape a matched L7 application (nDPI)


class Direction(str, Enum):
    DOWNLOAD = "download"    # toward the subscriber
    UPLOAD = "upload"        # toward the internet


@dataclass
class TimeWindow:
    """A schedule window for TIME_BASED pipes (24h clock, subscriber TZ)."""
    name: str
    days: list[int]              # 0=Mon .. 6=Sun
    start: str                   # "HH:MM"
    end: str                     # "HH:MM"
    download_mbps: float
    upload_mbps: float


@dataclass
class Subscriber:
    """A billed endpoint: one public IP or a CIDR network group."""
    ref: str                     # customer reference / account id
    cidr: str                    # "203.0.113.4/32" or "203.0.113.0/24"
    download_mbps: float         # plan (ceil) rate
    upload_mbps: float


@dataclass
class Pipe:
    """A single bandwidth package instance to be enforced."""
    id: int
    name: str
    ptype: PipeType
    download_mbps: float = 0.0
    upload_mbps: float = 0.0
    # CONTENDED
    contention_ratio: int = 1            # N in 1:N (1 == dedicated behaviour)
    subscribers: list[Subscriber] = field(default_factory=list)
    # PROTOCOL / APPLICATION  (match set by the DPI classifier as an fwmark)
    match_label: Optional[str] = None    # e.g. "bittorrent", "netflix", "quic"
    fwmark: Optional[int] = None         # firewall mark the DPI engine assigns
    # TIME_BASED
    windows: list[TimeWindow] = field(default_factory=list)
    # priority: lower = higher priority (HTB prio 0..7)
    priority: int = 3


@dataclass
class InterfacePlan:
    """Everything to be shaped on one physical direction of the bridge."""
    interface: str                       # e.g. "eth0" (subscriber side) / "eth1" (net side)
    direction: Direction
    total_mbps: float                    # link capacity in this direction
    pipes: list[Pipe] = field(default_factory=list)
