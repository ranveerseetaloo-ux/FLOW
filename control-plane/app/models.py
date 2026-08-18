"""
ORM models — the management/inventory database (PostgreSQL in prod, SQLite in dev).

This is the NetXplorer-equivalent config store: customers, their public IPs /
network groups, the pipes (bandwidth packages) and the subscriber<->pipe
assignments, plus operator users and an audit log.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# reuse the canonical pipe-type enum from the data plane
from shaper.models import PipeType  # type: ignore  (path bootstrapped in config)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    ip_groups: Mapped[list["IPGroup"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class IPGroup(Base):
    """A public IP (/32) or a network group (CIDR) that carries traffic."""
    __tablename__ = "ip_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    cidr: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    pipe_id: Mapped[int | None] = mapped_column(ForeignKey("pipes.id", ondelete="SET NULL"), nullable=True)
    # per-assignment plan overrides (Mbps); fall back to the pipe defaults if 0
    download_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    upload_mbps: Mapped[float] = mapped_column(Float, default=0.0)

    customer: Mapped["Customer"] = relationship(back_populates="ip_groups")
    pipe: Mapped["Pipe | None"] = relationship(back_populates="members")

    __table_args__ = (UniqueConstraint("cidr", name="uq_ipgroup_cidr"),)


class Pipe(Base):
    """A bandwidth package definition."""
    __tablename__ = "pipes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    ptype: Mapped[PipeType] = mapped_column(Enum(PipeType), index=True)
    download_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    upload_mbps: Mapped[float] = mapped_column(Float, default=0.0)
    contention_ratio: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    # protocol / application shaping
    match_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fwmark: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # time-based windows serialized as JSON text
    windows_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    members: Mapped[list["IPGroup"]] = relationship(back_populates="pipe")


class User(Base):
    """Operator login (RBAC)."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin|operator|viewer
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text, default="")
