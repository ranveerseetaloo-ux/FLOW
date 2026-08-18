"""
Policy compiler bridge.

Converts the control-plane's stored pipes + IP-group assignments into the
data-plane's InterfacePlan, then compiles it to tc commands. Deliberately
duck-typed: it reads plain attributes, so it works with SQLAlchemy ORM objects,
pydantic schemas, or SimpleNamespace stubs — which keeps it unit-testable
without a database.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from shaper.models import (  # type: ignore
    Direction, InterfacePlan, Pipe, PipeType, Subscriber, TimeWindow,
)
from shaper.tc_compiler import TcProgram, compile_plan


def _plan_rate(assignment: Any, pipe: Any, download: bool) -> float:
    """Assignment override wins; else the pipe's own default."""
    a = assignment.download_mbps if download else assignment.upload_mbps
    if a and a > 0:
        return float(a)
    return float(pipe.download_mbps if download else pipe.upload_mbps)


def _windows(pipe: Any) -> list[TimeWindow]:
    raw = getattr(pipe, "windows_json", None)
    if not raw:
        # pydantic PipeIn carries `windows` directly
        wins = getattr(pipe, "windows", None) or []
        return [TimeWindow(w.name, w.days, w.start, w.end, w.download_mbps, w.upload_mbps)
                for w in wins]
    data = json.loads(raw)
    return [TimeWindow(**w) for w in data]


def build_interface_plan(
    *,
    interface: str,
    direction: Direction,
    total_mbps: float,
    pipes: Iterable[Any],
    assignments: Iterable[Any],
) -> InterfacePlan:
    """Assemble a data-plane InterfacePlan from stored objects."""
    by_pipe: dict[int, list[Any]] = {}
    for a in assignments:
        if a.pipe_id is not None:
            by_pipe.setdefault(a.pipe_id, []).append(a)

    dp_pipes: list[Pipe] = []
    download = direction == Direction.DOWNLOAD
    for p in pipes:
        subs = [
            Subscriber(
                ref=getattr(a, "ref", getattr(a, "label", "") or a.cidr),
                cidr=a.cidr,
                download_mbps=_plan_rate(a, p, True),
                upload_mbps=_plan_rate(a, p, False),
            )
            for a in by_pipe.get(p.id, [])
        ]
        dp_pipes.append(
            Pipe(
                id=p.id,
                name=p.name,
                ptype=PipeType(p.ptype) if not isinstance(p.ptype, PipeType) else p.ptype,
                download_mbps=float(p.download_mbps),
                upload_mbps=float(p.upload_mbps),
                contention_ratio=int(getattr(p, "contention_ratio", 1)),
                subscribers=subs,
                match_label=getattr(p, "match_label", None),
                fwmark=getattr(p, "fwmark", None),
                windows=_windows(p),
                priority=int(getattr(p, "priority", 3)),
            )
        )
    return InterfacePlan(interface=interface, direction=direction,
                         total_mbps=float(total_mbps), pipes=dp_pipes)


def compile_interface(**kwargs: Any) -> TcProgram:
    return compile_plan(build_interface_plan(**kwargs))
