"""Pipe (bandwidth package) CRUD."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Pipe
from ..schemas import PipeIn, PipeOut
from .auth import require

router = APIRouter(prefix="/pipes", tags=["pipes"])


@router.get("", response_model=list[PipeOut])
def list_pipes(db: Session = Depends(get_db)):
    return db.scalars(select(Pipe).order_by(Pipe.id)).all()


@router.post("", response_model=PipeOut, status_code=201)
def create_pipe(body: PipeIn, db: Session = Depends(get_db), _=Depends(require("operator"))):
    if db.scalar(select(Pipe).where(Pipe.name == body.name)):
        raise HTTPException(409, "pipe name already exists")
    data = body.model_dump()
    windows = data.pop("windows", [])
    p = Pipe(**data, windows_json=json.dumps(windows) if windows else None)
    db.add(p)
    db.commit()
    return p


@router.get("/{pid}", response_model=PipeOut)
def get_pipe(pid: int, db: Session = Depends(get_db)):
    p = db.get(Pipe, pid)
    if not p:
        raise HTTPException(404, "not found")
    return p


@router.delete("/{pid}", status_code=204)
def delete_pipe(pid: int, db: Session = Depends(get_db), _=Depends(require("admin"))):
    p = db.get(Pipe, pid)
    if p:
        db.delete(p)
        db.commit()
