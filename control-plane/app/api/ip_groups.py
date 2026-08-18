"""IP group (public IP / CIDR) CRUD and pipe assignment."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Customer, IPGroup, Pipe
from ..schemas import IPGroupIn, IPGroupOut
from .auth import require

router = APIRouter(prefix="/ip-groups", tags=["ip-groups"])


@router.get("", response_model=list[IPGroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.scalars(select(IPGroup).order_by(IPGroup.id)).all()


@router.post("", response_model=IPGroupOut, status_code=201)
def create_group(body: IPGroupIn, db: Session = Depends(get_db), _=Depends(require("operator"))):
    if not db.get(Customer, body.customer_id):
        raise HTTPException(404, "customer not found")
    if body.pipe_id is not None and not db.get(Pipe, body.pipe_id):
        raise HTTPException(404, "pipe not found")
    if db.scalar(select(IPGroup).where(IPGroup.cidr == body.cidr)):
        raise HTTPException(409, "cidr already registered")
    g = IPGroup(**body.model_dump())
    db.add(g)
    db.commit()
    return g


@router.patch("/{gid}/assign/{pipe_id}", response_model=IPGroupOut)
def assign_pipe(gid: int, pipe_id: int, db: Session = Depends(get_db), _=Depends(require("operator"))):
    g = db.get(IPGroup, gid)
    if not g:
        raise HTTPException(404, "ip group not found")
    if not db.get(Pipe, pipe_id):
        raise HTTPException(404, "pipe not found")
    g.pipe_id = pipe_id
    db.commit()
    return g


@router.delete("/{gid}", status_code=204)
def delete_group(gid: int, db: Session = Depends(get_db), _=Depends(require("admin"))):
    g = db.get(IPGroup, gid)
    if g:
        db.delete(g)
        db.commit()
