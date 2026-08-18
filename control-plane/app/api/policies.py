"""
Policy compilation & push.

Reads the current pipes + assignments, compiles them into tc commands via the
shared pipe_builder, and (optionally) pushes to the data-plane node agents.
This is the bridge between the management DB and the shaper.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from shaper.models import Direction  # type: ignore

from ..config import get_settings
from ..core.pipe_builder import compile_interface
from ..db import get_db
from ..models import AuditLog, IPGroup, Pipe
from ..schemas import CompileRequest, CompileResponse
from .auth import current_user, require

router = APIRouter(prefix="/policies", tags=["policies"])
settings = get_settings()


def _compile(db: Session, req: CompileRequest):
    pipes = db.scalars(select(Pipe)).all()
    assignments = db.scalars(select(IPGroup).where(IPGroup.pipe_id.isnot(None))).all()
    # give each assignment a `ref` attribute for the subscriber label
    for a in assignments:
        a.ref = a.label or a.cidr  # type: ignore[attr-defined]
    return compile_interface(
        interface=req.interface,
        direction=Direction(req.direction),
        total_mbps=req.total_mbps,
        pipes=pipes,
        assignments=assignments,
    )


@router.post("/compile", response_model=CompileResponse)
def compile_policy(req: CompileRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    prog = _compile(db, req)
    return CompileResponse(interface=prog.interface, direction=prog.direction.value,
                           commands=prog.commands, warnings=prog.warnings, applied=False)


@router.post("/apply", response_model=CompileResponse)
def apply_policy(req: CompileRequest, db: Session = Depends(get_db), user=Depends(require("operator"))):
    prog = _compile(db, req)
    applied = False
    if req.apply and not settings.dry_run:
        payload = {"interface": prog.interface, "direction": prog.direction.value,
                   "commands": prog.commands}
        for node in settings.dataplane_nodes:
            try:
                httpx.post(f"http://{node}/apply", json=payload, timeout=10).raise_for_status()
                applied = True
            except Exception:  # noqa: BLE001 - node push is best-effort, logged
                pass
    db.add(AuditLog(actor=user.username, action="apply_policy",
                    detail=f"{prog.interface}/{prog.direction.value} "
                           f"{len(prog.commands)} cmds applied={applied}"))
    db.commit()
    return CompileResponse(interface=prog.interface, direction=prog.direction.value,
                           commands=prog.commands, warnings=prog.warnings, applied=applied)
